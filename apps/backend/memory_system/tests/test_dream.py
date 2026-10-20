"""Daily consolidation, retry checkpoints, profile changes and cross-session context."""

import asyncio
import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from memory_system.api import router
from memory_system.dream import DailySummaryORM, DreamConsolidator, MemoryMaintenanceScheduler, profile_changes
from memory_system.importance import enrich_frequency
from memory_system.recall import recall_memory
from memory_system.session_store import ConversationTurnORM, PersistentSessionMemory
from memory_system.vector_store import store_memory
from memory_system.working import WorkingMemory
from shared_contracts.models import MemoryEntry, PersonaProfile
from shared_runtime.database import AsyncSessionLocal, init_database_schema
from shared_runtime.prompt_engine import build_conversation_system_prompt


@pytest.fixture(autouse=True)
async def services(monkeypatch):
    await init_database_schema()
    monkeypatch.setattr("memory_system.vector_store._get_embedding", AsyncMock(return_value=[1.0, 0.0]))
    monkeypatch.setattr(
        "memory_system.dream.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "memory_dream_use_llm": False,
                "memory_timezone": "Asia/Shanghai",
                "memory_maintenance_interval_seconds": 3600,
            },
        )(),
    )


async def turn_at(user, message, timestamp, *, emotion="neutral", session_id=None):
    history = PersistentSessionMemory()
    sid, tid = session_id or uuid4().hex, uuid4().hex
    await history.add_turn(sid, tid, message, "我在听", metadata={"user_id": user, "emotion": emotion})
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(ConversationTurnORM).where(
                    ConversationTurnORM.session_id == sid,
                    ConversationTurnORM.turn_id == tid,
                )
            )
        ).scalar_one()
        payload = json.loads(row.payload_json)
        payload["timestamp"] = timestamp.isoformat()
        row.payload_json = json.dumps(payload, ensure_ascii=False)
        await session.commit()
    return sid


async def test_daily_consolidation_uses_user_day_and_checkpoint_without_repeat_calls():
    user = uuid4().hex
    await turn_at(user, "我叫小林，我喜欢散步", datetime(2026, 10, 18, 18, tzinfo=UTC))  # 19th in Shanghai
    await turn_at(user, "我现在不喜欢咖啡", datetime(2026, 10, 19, 2, tzinfo=UTC), emotion="sad")
    await turn_at(user, "下一天的对话", datetime(2026, 10, 19, 18, tzinfo=UTC))
    model = AsyncMock(return_value="用户喜欢散步，开始减少咖啡。")
    observer = AsyncMock()
    dream = DreamConsolidator(summary_generator=model, profile_observer=observer)
    result = await dream.consolidate(user, date(2026, 10, 19))
    assert result["turn_count"] == 2
    assert result["profile_changes"]["likes"] == ["散步"]
    assert result["profile_changes"]["dislikes"] == ["咖啡"]
    assert result["mood_counts"]["sad"] == 1
    assert result["profile_sync_pending"] is False
    observer.assert_awaited_once()
    restarted = DreamConsolidator(summary_generator=model, profile_observer=observer)
    assert (await restarted.consolidate(user, date(2026, 10, 19)))["status"] == "unchanged"
    model.assert_awaited_once()
    observer.assert_awaited_once()


async def test_profile_retry_does_not_repeat_summary_generation():
    user = uuid4().hex
    await turn_at(user, "我喜欢散步", datetime(2026, 10, 19, 3, tzinfo=UTC))
    model = AsyncMock(return_value="今日回顾")
    observer = AsyncMock(side_effect=RuntimeError("temporarily offline"))
    dream = DreamConsolidator(summary_generator=model, profile_observer=observer)
    assert (await dream.consolidate(user, date(2026, 10, 19)))["profile_sync_pending"]
    observer.side_effect = None
    result = await dream.consolidate(user, date(2026, 10, 19))
    assert not result["profile_sync_pending"]
    assert observer.await_count == 2
    model.assert_awaited_once()


async def test_relationship_review_retry_preserves_summary_checkpoint():
    user = uuid4().hex
    await turn_at(user, "其实我喜欢散步", datetime(2026, 10, 19, 3, tzinfo=UTC))
    model = AsyncMock(return_value="今日回顾")
    observer = AsyncMock(side_effect=RuntimeError("temporarily offline"))
    dream = DreamConsolidator(summary_generator=model, relationship_observer=observer)
    first = await dream.consolidate(user, date(2026, 10, 19))
    assert first["relationship_review"]["status"] == "pending"
    observer.side_effect = None
    observer.return_value = {"status": "updated", "observed_turns": 1}
    second = await dream.consolidate(user, date(2026, 10, 19))
    assert second["relationship_review"]["status"] == "updated"
    assert observer.await_count == 2
    model.assert_awaited_once()


async def test_summary_failure_preserves_explicit_user_excerpt():
    user = uuid4().hex
    await turn_at(user, "我明天要面试", datetime(2026, 10, 19, 3, tzinfo=UTC))
    dream = DreamConsolidator(summary_generator=AsyncMock(side_effect=TimeoutError()))
    result = await dream.consolidate(user, date(2026, 10, 19))
    assert result["method"] == "extractive"
    assert "我明天要面试" in result["summary"]


async def test_scheduler_only_consolidates_during_local_idle_window():
    user = uuid4().hex
    await turn_at(user, "我喜欢散步", datetime(2026, 10, 19, 1, tzinfo=UTC))
    dream = DreamConsolidator(summary_generator=AsyncMock(return_value="一天的回顾"))
    dream.history.users = AsyncMock(return_value=[user])
    scheduler = MemoryMaintenanceScheduler(dream)
    result = await scheduler.tick(datetime(2026, 10, 19, 20, tzinfo=UTC))  # Shanghai 20th 04:00
    assert result["days_consolidated"] == 1
    assert (await scheduler.tick(datetime(2026, 10, 19, 21, tzinfo=UTC)))["days_consolidated"] == 0
    dream.summary_generator.reset_mock()
    assert (await scheduler.tick(datetime(2026, 10, 20, 9, tzinfo=UTC)))["days_consolidated"] == 0
    dream.summary_generator.assert_not_called()


async def test_new_session_prompt_contains_only_owners_previous_context():
    user, other = uuid4().hex, uuid4().hex
    memory = WorkingMemory(window_size=1)
    sid = uuid4().hex
    await memory.observe_turn(sid, "a", "我下周有面试", "我陪你准备", user_id=user)
    await memory.observe_turn(sid, "b", "先休息一下", "好的", user_id=user)
    foreign = WorkingMemory(window_size=1)
    await foreign.observe_turn(uuid4().hex, "a", "别人的私密信息", "好的", user_id=other)
    await DreamConsolidator(summary_generator=AsyncMock(return_value="回顾：用户准备面试")).consolidate(user)
    async with AsyncSessionLocal() as session:
        recalled = await recall_memory(session, user, "面试", session_id=uuid4().hex)
    assert "面试" in recalled.previous_session_digest
    assert "面试" in recalled.daily_summary
    prompt = build_conversation_system_prompt(persona=PersonaProfile(name="Companion"), memory=recalled)
    assert "此前会话回顾" in prompt and "对话日总结" in prompt
    assert "别人的私密信息" not in prompt


async def test_actual_repeat_frequency_is_user_scoped_and_not_client_controlled():
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        await store_memory(session, MemoryEntry(entry_id="", user_id=user, category="preference", content="我喜欢散步"))
        await store_memory(
            session, MemoryEntry(entry_id="", user_id="other", category="preference", content="我喜欢散步")
        )
    data = await enrich_frequency(
        {"user_id": user, "user_message": "我喜欢散步", "metadata": {"occurrence_count": 1000}}
    )
    assert data["metadata"]["occurrence_count"] == 2


async def test_daily_summary_api_is_user_scoped_and_validates_date(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    user, other = uuid4().hex, uuid4().hex
    await turn_at(user, "今天想休息", datetime.now(UTC))
    injected = DreamConsolidator(summary_generator=AsyncMock(return_value="用户想休息"))
    monkeypatch.setattr("memory_system.api.dream_consolidator", injected)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/memory/user/{user}/consolidate", json={})).status_code == 200
        assert len((await client.get(f"/memory/user/{user}/daily_summaries")).json()) == 1
        assert (await client.get(f"/memory/user/{other}/daily_summaries")).json() == []
        assert (await client.post(f"/memory/user/{user}/consolidate", json={"day": "invalid"})).status_code == 422


def test_latest_explicit_preference_wins_without_assistant_invention():
    result = profile_changes(
        [
            {"user_message": "我喜欢咖啡", "assistant_message": "你最爱奶茶"},
            {"user_message": "我现在不再喜欢咖啡，我更喜欢茶"},
        ]
    )
    assert result == {"likes": ["茶"], "dislikes": ["咖啡"]}


async def test_two_consolidators_do_not_generate_the_same_day_concurrently():
    user = uuid4().hex
    await turn_at(user, "我喜欢散步", datetime.now(UTC))
    started, release = asyncio.Event(), asyncio.Event()

    async def generate(_):
        started.set()
        await release.wait()
        return "今日回顾"

    first = DreamConsolidator(summary_generator=generate)
    second = DreamConsolidator(summary_generator=AsyncMock(return_value="不应调用"))
    running = asyncio.create_task(first.consolidate(user))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        assert (await second.consolidate(user))["status"] == "busy"
        second.summary_generator.assert_not_called()
    finally:
        release.set()
        await running


async def test_deleting_source_during_generation_does_not_recreate_private_content():
    user = uuid4().hex
    await turn_at(user, "待删除的私人内容", datetime.now(UTC))

    async def generate(_):
        await PersistentSessionMemory().clear_user(user)
        return "不应保存的旧总结"

    dream = DreamConsolidator(summary_generator=generate)
    assert (await dream.consolidate(user))["status"] == "stale"
    async with AsyncSessionLocal() as session:
        assert (
            not (await session.execute(select(DailySummaryORM).where(DailySummaryORM.user_id == user))).scalars().all()
        )


async def test_clear_all_also_clears_recaps_and_previous_session_context():
    user, other = uuid4().hex, uuid4().hex
    memory = WorkingMemory(window_size=1)
    sid = uuid4().hex
    await memory.observe_turn(sid, "one", "我的旧信息", "好的", user_id=user)
    await memory.observe_turn(sid, "two", "接下来聊别的", "好的", user_id=user)
    await turn_at(other, "其他用户的记录", datetime.now(UTC))
    await DreamConsolidator(summary_generator=AsyncMock(return_value="旧信息回顾")).consolidate(user)
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.delete(f"/memory/user/{user}/all")).status_code == 200
    async with AsyncSessionLocal() as session:
        result = await recall_memory(session, user, "旧信息", session_id=uuid4().hex)
    assert result.previous_session_digest is None
    assert result.daily_summary is None
    assert len(await PersistentSessionMemory().user_turns(other)) == 1


async def test_clear_between_fingerprint_check_and_commit_invalidates_the_writer():
    user = uuid4().hex
    await turn_at(user, "待删除的旧信息", datetime.now(UTC))
    app = FastAPI()
    app.include_router(router)
    dream = DreamConsolidator(summary_generator=AsyncMock(return_value="旧信息总结"))

    async def delete_after_check(*_):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.delete(f"/memory/user/{user}/all")).status_code == 200
        return True

    dream._renew = delete_after_check
    assert (await dream.consolidate(user))["status"] == "stale"
    async with AsyncSessionLocal() as session:
        assert (
            not (await session.execute(select(DailySummaryORM).where(DailySummaryORM.user_id == user))).scalars().all()
        )


async def test_cancellation_releases_daily_lease_for_the_next_attempt():
    user = uuid4().hex
    await turn_at(user, "我喜欢散步", datetime.now(UTC))
    started = asyncio.Event()

    async def wait_for_cancel(_):
        started.set()
        await asyncio.Event().wait()

    dream = DreamConsolidator(summary_generator=wait_for_cancel)
    task = asyncio.create_task(dream.consolidate(user))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    retry = DreamConsolidator(summary_generator=AsyncMock(return_value="重试后保存"))
    assert (await retry.consolidate(user))["status"] == "updated"
