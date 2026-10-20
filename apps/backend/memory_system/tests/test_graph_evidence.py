from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update

from memory_system.api import delete_all_user_memories
from memory_system.graph_lifecycle import GraphMemoryDeletionORM, cleanup_pending, retry_cleanup
from memory_system.graph_store import graph_store
from memory_system.lifecycle import MemoryStateORM
from memory_system.recall import recall_memory
from memory_system.vector_store import delete_memory_by_id, store_memory
from shared_contracts import MemoryEntry
from shared_runtime.database import AsyncSessionLocal, init_database_schema


@pytest.mark.parametrize("change", ["delete", "fade", "clear"])
async def test_late_external_result_does_not_restore_sql_source_or_profile_summary(monkeypatch, change):
    await init_database_schema()
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        entry = await store_memory(
            session,
            MemoryEntry(
                entry_id="", user_id=user, category="fact", content="trace-source old-target", embedding=[1.0, 0.0]
            ),
            extracted={"relationships": [{"source": "trace-source", "target": "old-target", "type": "REMEMBERS"}]},
        )

    async def late_graph(user_id, memory_ids, limit):
        assert entry.entry_id in memory_ids
        async with AsyncSessionLocal() as session:
            if change == "delete":
                assert await delete_memory_by_id(session, entry.entry_id)
            elif change == "fade":
                await session.execute(
                    update(MemoryStateORM)
                    .where(MemoryStateORM.memory_id == entry.entry_id)
                    .values(dormant_since=datetime.now(UTC))
                )
                await session.commit()
            else:
                await delete_all_user_memories(user, session)
        return [{"memory_id": entry.entry_id, "text": "private late fact"}]

    monkeypatch.setattr(graph_store, "_driver", object())
    monkeypatch.setattr(graph_store, "get_memory_facts", late_graph)
    monkeypatch.setattr("memory_system.vector_store._get_embedding", AsyncMock(return_value=[1.0, 0.0]))
    monkeypatch.setattr("memory_system.recall._fetch_relationship_metrics", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "memory_system.recall.settings", SimpleNamespace(enable_local_memory_graph=True, enable_knowledge_graph=True)
    )
    async with AsyncSessionLocal() as session:
        result = await recall_memory(session, user, "trace-source")
    assert result.entries == []
    assert result.graph_facts == []
    assert result.user_profile_summary is None


async def test_clear_during_embedding_does_not_reinforce_a_new_generation(monkeypatch):
    await init_database_schema()
    user, stored = uuid4().hex, []

    async def embedding(query):
        async with AsyncSessionLocal() as session:
            await delete_all_user_memories(user, session)
            entry = await store_memory(
                session,
                MemoryEntry(entry_id="", user_id=user, category="fact", content="new generation", embedding=[1.0, 0.0]),
            )
            stored.append(entry.entry_id)
        return [1.0, 0.0]

    monkeypatch.setattr("memory_system.vector_store._get_embedding", embedding)
    monkeypatch.setattr("memory_system.recall._fetch_relationship_metrics", AsyncMock(return_value=None))
    async with AsyncSessionLocal() as session:
        result = await recall_memory(session, user, "query")
        states = list(await session.scalars(select(MemoryStateORM).where(MemoryStateORM.user_id == user)))
    assert result.entries == [] and result.graph_facts == []
    assert [state.memory_id for state in states] == stored and states[0].access_count == 0


async def test_cleanup_scan_reaches_later_users_despite_a_failed_first_user(monkeypatch):
    await init_database_schema()
    prefix = "zzzz-fair-" + uuid4().hex
    users = [prefix + suffix for suffix in "abcdef"]
    async with AsyncSessionLocal() as session:
        session.add_all([GraphMemoryDeletionORM(user_id=user, memory_id=str(uuid4())) for user in users])
        await session.commit()

    async def delete_graph(user, ids):
        if user == users[0]:
            raise RuntimeError("offline")

    monkeypatch.setattr(graph_store, "delete_memory_graphs", delete_graph)
    try:
        cursor = await retry_cleanup(prefix)
        assert cursor == users[3]
        cursor = await retry_cleanup(cursor)
        assert cursor == users[5]
        assert await cleanup_pending(users[0])
        assert not any([await cleanup_pending(user) for user in users[1:]])
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(GraphMemoryDeletionORM).where(GraphMemoryDeletionORM.user_id.in_(users)))
            await session.commit()
