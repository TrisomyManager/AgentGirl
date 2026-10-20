"""Behavioral contracts for forgetting, recall fusion, graph diffusion and rule scoring."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from memory_system.db import MemoryORM
from memory_system.graph_index import MemoryEntityLinkORM, MemoryGraphIndexORM, MemoryRelationORM, backfill_graph
from memory_system.importance import apply_importance, ground_extraction, importance_evidence
from memory_system.lifecycle import MemoryStateORM, record_recall, restore_memory, run_forgetting
from memory_system.pipeline import _stage3_score, _stage5_store, stage3_importance_scoring
from memory_system.recall import fuse_candidates, recall_memory
from memory_system.vector_store import delete_memory_by_id, list_user_memories, store_memory
from shared_contracts.models import MemoryCategory, MemoryEntry
from shared_runtime.database import AsyncSessionLocal, init_database_schema


@pytest.fixture(autouse=True)
async def isolated_services(monkeypatch):
    await init_database_schema()
    from memory_system.recall import settings

    monkeypatch.setattr(settings, "enable_knowledge_graph", True)

    async def embedding(text):
        return [1.0, 0.0, 0.0] if any(word in text for word in ("猫", "咪咪")) else [0.0, 1.0, 0.0]

    monkeypatch.setattr("memory_system.vector_store._get_embedding", embedding)


async def add_memory(session, user, content, importance=0.5, days_old=0, expires_at=None, extracted=None):
    entry = MemoryEntry(
        entry_id="",
        user_id=user,
        category=MemoryCategory.FACT,
        content=content,
        importance=importance,
        created_at=datetime.now(UTC) - timedelta(days=days_old),
        expires_at=expires_at,
    )
    return await store_memory(session, entry, extracted=extracted)


async def test_forgetting_is_reversible_and_independent_of_maintenance_frequency():
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        old = await add_memory(session, user, "猫以前住在这里", importance=0.25, days_old=365)
        vital = await add_memory(session, user, "记住我对花生过敏", importance=0.95, days_old=365)
        now = datetime.now(UTC)
        first = await run_forgetting(session, user, now, batch_size=1)
        second = await run_forgetting(session, user, now)
        assert first["newly_dormant"] == 1
        assert second["newly_dormant"] == second["decayed"] == 0
        listed = {entry.entry_id: entry for entry in await list_user_memories(session, user)}
        assert listed[old.entry_id].memory_status == "dormant"
        assert listed[vital.entry_id].memory_status == "active"
        assert listed[old.entry_id].importance == 0.25
        assert (
            await session.execute(select(func.count()).select_from(MemoryORM).where(MemoryORM.user_id == user))
        ).scalar_one() == 2
        recalled = await recall_memory(session, user, "猫以前住在这里", top_k=1)
        assert recalled.entries[0].entry_id == old.entry_id
        assert (await session.get(MemoryStateORM, old.entry_id, populate_existing=True)).dormant_since is None


async def test_access_frequency_slows_decay():
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        rare = await add_memory(session, user, "旧的普通事情", importance=0.3, days_old=120)
        frequent = await add_memory(session, user, "经常想起的事情", importance=0.3, days_old=120)
        state = await session.get(MemoryStateORM, frequent.entry_id)
        state.access_count = 100
        await session.commit()
        await run_forgetting(session, user)
        states = {entry.entry_id: entry for entry in await list_user_memories(session, user)}
        assert states[frequent.entry_id].effective_importance > states[rare.entry_id].effective_importance
        assert states[frequent.entry_id].memory_status == "active"
        assert states[rare.entry_id].memory_status == "dormant"


async def test_expired_memories_are_hidden_until_owner_restores_them():
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        expired = await add_memory(
            session, user, "猫的旧约定", importance=0.9, expires_at=datetime.now(UTC) - timedelta(days=1)
        )
        assert not (await recall_memory(session, user, "猫的旧约定")).entries
        assert not await restore_memory(session, "different-user", expired.entry_id)
        assert await restore_memory(session, user, expired.entry_id)
        entries = (await recall_memory(session, user, "猫的旧约定")).entries
        assert entries[0].entry_id == expired.entry_id
        assert entries[0].expires_at is None


async def test_graph_retrieval_finds_related_memory_and_isolates_users():
    user, other = uuid4().hex, uuid4().hex
    async with AsyncSessionLocal() as session:
        first = await add_memory(session, user, "猫咪咪是家里的宠物", extracted={"entities": [{"name": "咪咪"}]})
        related = await add_memory(
            session,
            user,
            "宠物明天去复诊",
            extracted={
                "entities": [{"name": "咪咪"}, {"name": "李医生"}],
                "relationships": [{"source": "咪咪", "target": "李医生", "type": "HAS_DOCTOR"}],
            },
        )
        private = await add_memory(
            session, other, "猫咪咪的另一位用户的秘密", extracted={"entities": [{"name": "咪咪"}]}
        )
        result = await recall_memory(session, user, "咪咪", top_k=5)
        identities = {entry.entry_id for entry in result.entries}
        assert {first.entry_id, related.entry_id} <= identities
        assert private.entry_id not in identities
        assert any("HAS_DOCTOR" in fact for fact in result.graph_facts)
        state = await session.get(MemoryStateORM, related.entry_id, populate_existing=True)
        assert state.access_count == 1


async def test_explicit_delete_also_removes_retrieval_metadata():
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        entry = await add_memory(
            session,
            user,
            "猫的关系",
            extracted={
                "relationships": [
                    {"source": "咪咪", "target": "兽医", "type": "VISITS"},
                ]
            },
        )
        await record_recall(session, user, [entry])
        await session.commit()
        assert await delete_memory_by_id(session, entry.entry_id)
        for model, column in (
            (MemoryStateORM, MemoryStateORM.memory_id),
            (MemoryEntityLinkORM, MemoryEntityLinkORM.memory_id),
            (MemoryRelationORM, MemoryRelationORM.memory_id),
        ):
            assert not (await session.execute(select(model).where(column == entry.entry_id))).scalars().all()


async def test_generic_entity_cue_does_not_reveal_dormant_relation():
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        old = await add_memory(
            session, user, "旧的普通事情", importance=0.2, days_old=365,
            extracted={"relationships": [{"source": "咪咪", "target": "旧诊所", "type": "VISITS"}]},
        )
        await add_memory(session, user, "猫咪咪今天在家", extracted={"entities": [{"name": "咪咪"}]})
        await run_forgetting(session, user)
        result = await recall_memory(session, user, "咪咪")
        assert old.entry_id not in {entry.entry_id for entry in result.entries}
        assert not any("旧诊所" in fact for fact in result.graph_facts)
        assert (await session.get(MemoryStateORM, old.entry_id, populate_existing=True)).dormant_since is not None


def test_fusion_rewards_agreement_and_drops_weak_semantic_noise():
    a = MemoryEntry(entry_id="a", user_id="u", category="fact", content="a", similarity=0.9)
    b = MemoryEntry(entry_id="b", user_id="u", category="fact", content="b", similarity=0.8)
    noise = MemoryEntry(entry_id="noise", user_id="u", category="fact", content="noise", similarity=0.01)
    assert [entry.entry_id for entry in fuse_candidates([a, b, noise], [b], 3)] == ["b", "a"]


def test_importance_uses_user_evidence_and_finite_scores():
    assert importance_evidence({"user_message": "好的", "assistant_message": "生日和重要约定"}).score == 0.1
    remembered = apply_importance({"user_message": "请记住我对花生过敏"}, {"importance": 0.05})
    assert remembered["importance"] >= 0.9
    assert apply_importance({"user_message": "我喜欢散步"}, {"importance": float("nan")})["importance"] == 0.75
    first = importance_evidence({"user_message": "我喜欢散步"})
    repeated = importance_evidence({"user_message": "我喜欢散步", "metadata": {"occurrence_count": 4}})
    assert repeated.score > first.score


async def test_pipeline_score_rules_work_without_llm_and_skip_acknowledgements(monkeypatch):
    model = AsyncMock(side_effect=RuntimeError("offline"))
    monkeypatch.setattr("memory_system.pipeline._llm_chat", model)
    scored = await _stage3_score({"user_message": "请记住我对花生过敏"})
    assert scored["importance"] >= 0.9
    model.reset_mock()
    assert (await _stage3_score({"user_message": "好的"}))["importance"] == 0.1
    model.assert_not_called()
    assert stage3_importance_scoring.run({"user_message": "嗯"})["importance"] == 0.1


def test_extraction_does_not_promote_assistant_invention_to_a_user_fact():
    extracted = ground_extraction(
        {
            "entities": [{"name": "散步"}, {"name": "咖啡", "properties": {"favorite": True}}],
            "preferences": [{"key": "activity", "value": "散步"}, {"key": "drink", "value": "咖啡"}],
            "relationships": [{"source": "散步", "target": "咖啡", "type": "PREFERS"}],
        },
        "我喜欢散步",
    )
    assert [entity["name"] for entity in extracted["entities"]] == ["散步"]
    assert extracted["relationships"] == []
    assert extracted["preferences"] == [{"key": "activity", "value": "散步"}]


async def test_acknowledgement_does_not_create_a_permanent_fact():
    result = await _stage5_store({"user_message": "好的"})
    assert result["memory_entry_id"] is None
    assert result["memory_skipped"] == "low_information"


async def test_old_memories_gain_graph_indexes_and_even_empty_entries_are_checkpointed():
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        entry = await add_memory(session, user, "猫以前有个约定")
        from memory_system.graph_index import delete_graph_index

        await delete_graph_index(session, memory_id=entry.entry_id)
        await session.commit()
        assert await backfill_graph(session) >= 1
        assert await session.get(MemoryGraphIndexORM, entry.entry_id) is not None
        assert await backfill_graph(session) == 0


async def test_lite_reader_does_not_block_a_concurrent_memory_commit():
    user = uuid4().hex
    async with AsyncSessionLocal() as reader:
        await reader.execute(text("BEGIN"))
        await reader.execute(select(MemoryORM.id).limit(1))
        async with AsyncSessionLocal() as writer:
            entry = await asyncio.wait_for(add_memory(writer, user, "读写并发时仍可保存"), timeout=2)
            assert entry.entry_id
        await reader.rollback()


def test_memory_json_marks_legacy_naive_timestamps_as_utc():
    entry = MemoryEntry(entry_id="m", user_id="u", category="fact", content="过去的记忆",
                        created_at=datetime(2026, 10, 19, 11, 20))
    serialized = entry.model_dump(mode="json")["created_at"]
    assert datetime.fromisoformat(serialized) == datetime(2026, 10, 19, 11, 20, tzinfo=UTC)
    assert MemoryEntry.model_json_schema(mode="serialization")["properties"]["created_at"]["format"] == "date-time"
