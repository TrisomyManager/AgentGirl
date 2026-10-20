import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from memory_system.api import delete_all_user_memories
from memory_system.lifecycle import StaleMemoryWriteError, capture_memory_epoch
from memory_system.pipeline import run_pipeline_async
from memory_system.vector_store import list_user_memories, store_memory
from shared_contracts.models import MemoryEntry
from shared_runtime.database import AsyncSessionLocal, init_database_schema


async def clear(user):
    async with AsyncSessionLocal() as session:
        await delete_all_user_memories(user, session)


async def test_clear_during_embedding_prevents_old_write_and_allows_new_data(monkeypatch):
    await init_database_schema()
    user = uuid4().hex
    started, resume = asyncio.Event(), asyncio.Event()

    async def embedding(content):
        started.set()
        await resume.wait()
        return [1.0, 0.0]

    monkeypatch.setattr("memory_system.vector_store._get_embedding", embedding)

    async def write():
        async with AsyncSessionLocal() as session:
            await store_memory(session, MemoryEntry(
                entry_id="", user_id=user, category="fact", content="清空前的旧内容",
            ))

    task = asyncio.create_task(write())
    await asyncio.wait_for(started.wait(), 2)
    await asyncio.wait_for(clear(user), 2)  # no DB write lock held across embedding
    resume.set()
    with pytest.raises(StaleMemoryWriteError):
        await task
    async with AsyncSessionLocal() as session:
        assert await list_user_memories(session, user) == []
        entry = await store_memory(session, MemoryEntry(
            entry_id="", user_id=user, category="fact", content="清空后新内容", embedding=[1.0, 0.0],
        ))
        assert [item.entry_id for item in await list_user_memories(session, user)] == [entry.entry_id]


async def test_clear_while_pipeline_extracts_discards_derived_memory(monkeypatch):
    await init_database_schema()
    user = uuid4().hex
    started, resume = asyncio.Event(), asyncio.Event()

    async def extract(td):
        started.set()
        await resume.wait()
        return td | {"extracted": {}, "importance": 0.9}

    async def unchanged(td):
        return td

    monkeypatch.setattr("memory_system.pipeline._stage2_extract", extract)
    monkeypatch.setattr("memory_system.pipeline._stage3_score", unchanged)
    monkeypatch.setattr("memory_system.vector_store._get_embedding", AsyncMock(return_value=[1.0, 0.0]))
    task = asyncio.create_task(run_pipeline_async({
        "user_id": user, "turn_id": uuid4().hex, "user_message": "记住我每天早上喝茶", "assistant_message": "好的",
    }))
    await asyncio.wait_for(started.wait(), 2)
    await clear(user)
    resume.set()
    result = await task
    assert result["memory_skipped"] == "user_cleared"
    async with AsyncSessionLocal() as session:
        assert await list_user_memories(session, user) == []


async def test_queued_pipeline_keeps_version_captured_before_clear(monkeypatch):
    await init_database_schema()
    user = uuid4().hex
    version = await capture_memory_epoch(user)
    await clear(user)

    async def unchanged(td):
        return td

    monkeypatch.setattr("memory_system.pipeline._stage2_extract", unchanged)
    monkeypatch.setattr("memory_system.pipeline._stage3_score", unchanged)
    monkeypatch.setattr("memory_system.vector_store._get_embedding", AsyncMock(return_value=[1.0, 0.0]))
    result = await run_pipeline_async({
        "user_id": user, "turn_id": uuid4().hex, "user_message": "记住我喜欢茶", "source_epoch": version,
    })
    assert result["memory_skipped"] == "user_cleared"
