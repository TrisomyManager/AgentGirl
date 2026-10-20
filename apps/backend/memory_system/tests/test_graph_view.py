from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from memory_system.graph_view import memory_graph
from memory_system.lifecycle import MemoryStateORM
from memory_system.vector_store import delete_memory_by_id, store_memory
from shared_contracts.models import MemoryEntry
from shared_runtime.database import AsyncSessionLocal, init_database_schema


@pytest.fixture(autouse=True)
async def schema():
    await init_database_schema()


async def add(session, user, content, **kwargs):
    return await store_memory(
        session,
        MemoryEntry(entry_id="", user_id=user, content=content, category="fact", embedding=[0.0] * 1024, **kwargs),
        extracted={
            "entities": [{"name": "杭州", "type": "place"}, {"name": "旅行", "type": "event"}],
            "relationships": [{"source": "旅行", "target": "杭州", "type": "LOCATED_IN"}],
        },
    )


async def test_graph_is_user_scoped_grounded_in_existing_memory_and_removed_after_deletion():
    alice, bob = uuid4().hex, uuid4().hex
    async with AsyncSessionLocal() as session:
        first = await add(session, alice, "计划去杭州旅行")
        second = await add(session, bob, "另一个用户的杭州私密计划")
        result = await memory_graph(session, alice, include_keywords=False)
        assert result["memory_count"] == 1
        assert second.entry_id not in str(result) and "另一个用户" not in str(result)
        assert not any(node["kind"] == "keyword" for node in result["nodes"])
        edges = [edge for edge in result["edges"] if edge["kind"] == "relation"]
        assert len(edges) == 1 and edges[0]["memory_ids"] == [first.entry_id]
        assert "embedding" not in str(result)
        assert await delete_memory_by_id(session, first.entry_id)
        assert (await memory_graph(session, alice))["nodes"] == []
        assert (await memory_graph(session, bob))["memory_count"] == 1


async def test_faded_or_expired_memory_is_opt_in_and_viewing_does_not_reactivate_it():
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        faded = await add(session, user, "较早的杭州旅行")
        await add(session, user, "已经过期的杭州计划", expires_at=datetime.now(UTC) - timedelta(days=1))
        await session.execute(
            update(MemoryStateORM)
            .where(MemoryStateORM.memory_id == faded.entry_id)
            .values(
                dormant_since=datetime.now(UTC),
                effective_importance=0.05,
                access_count=0,
            )
        )
        await session.commit()
        assert (await memory_graph(session, user))["memory_count"] == 0
        result = await memory_graph(session, user, include_dormant=True)
        assert result["memory_count"] == 2
        assert all(n["status"] == "dormant" for n in result["nodes"] if n["kind"] == "memory")
        state = await session.scalar(select(MemoryStateORM).where(MemoryStateORM.memory_id == faded.entry_id))
        assert state.access_count == 0 and state.dormant_since is not None


async def test_graph_limits_content_and_searches_literal_text_without_wildcard_expansion():
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        await add(session, user, "杭州旅行 " + "x" * 3000)
        await add(session, user, "100% 的旅行约定")
        result = await memory_graph(session, user, limit=1)
        assert result["truncated"] and result["memory_count"] == 1
        filtered = await memory_graph(session, user, query="%")
        assert filtered["memory_count"] == 1
        assert next(n for n in filtered["nodes"] if n["kind"] == "memory")["content"] == "100% 的旅行约定"
        by_entity = await memory_graph(session, user, query="杭州")
        assert by_entity["memory_count"] == 2
        large = next(n for n in by_entity["nodes"] if n.get("content", "").startswith("杭州旅行"))
        assert len(large["content"]) == 2000 and large["content_truncated"]
