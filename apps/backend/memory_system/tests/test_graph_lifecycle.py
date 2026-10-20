import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from memory_system.api import delete_all_user_memories
from memory_system.graph_lifecycle import cleanup_pending, write_extracted_graph
from memory_system.graph_store import graph_store
from memory_system.lifecycle import capture_memory_epoch
from memory_system.vector_store import store_memory
from shared_contracts import MemoryEntry
from shared_runtime.database import AsyncSessionLocal, init_database_schema


async def test_graph_clear_waits_for_old_writer_and_prevents_post_clear_replay(monkeypatch):
    await init_database_schema()
    user = uuid4().hex
    async with AsyncSessionLocal() as session:
        entry = await store_memory(
            session,
            MemoryEntry(
                entry_id="", user_id=user, category="fact", content="Synthetic graph source", embedding=[1.0, 0.0]
            ),
        )
    epoch = await capture_memory_epoch(user)
    entered, resume = asyncio.Event(), asyncio.Event()
    order = []

    async def old_write(*args, **kwargs):
        entered.set()
        await resume.wait()
        order.append("old-write-finished")

    async def erase(*args, **kwargs):
        order.append("graph-erased")

    monkeypatch.setattr(graph_store, "_driver", object())
    monkeypatch.setattr(graph_store, "store_memory_graph", old_write)
    monkeypatch.setattr(graph_store, "delete_user_data", erase)
    monkeypatch.setattr(
        "shared_runtime.config.get_settings", lambda: SimpleNamespace(lite_mode=False, enable_knowledge_graph=True)
    )
    writer = asyncio.create_task(write_extracted_graph(user, epoch, {}, memory_id=entry.entry_id))
    await entered.wait()

    async def clear():
        async with AsyncSessionLocal() as session:
            return await delete_all_user_memories(user, session)

    cleared = asyncio.create_task(clear())
    await asyncio.sleep(0)
    assert not cleared.done()
    resume.set()
    assert await writer
    assert (await cleared)["external_graph"] == "completed"
    assert order == ["old-write-finished", "graph-erased"]
    assert not await write_extracted_graph(user, epoch, {}, memory_id=entry.entry_id)
    assert not await cleanup_pending(user)


async def test_failed_graph_clear_is_durable_and_blocks_new_graph_writes_until_retry(monkeypatch):
    await init_database_schema()
    user = uuid4().hex
    monkeypatch.setattr(
        "shared_runtime.config.get_settings", lambda: SimpleNamespace(lite_mode=False, enable_knowledge_graph=True)
    )
    monkeypatch.setattr(graph_store, "_driver", object())
    monkeypatch.setattr(graph_store, "delete_user_data", AsyncMock(side_effect=RuntimeError("private diagnostic")))
    async with AsyncSessionLocal() as session:
        result = await delete_all_user_memories(user, session)
    assert result["external_graph"] == "pending"
    assert "private" not in str(result)
    assert await cleanup_pending(user)
    epoch = await capture_memory_epoch(user)
    async with AsyncSessionLocal() as session:
        entry = await store_memory(
            session,
            MemoryEntry(
                entry_id="",
                user_id=user,
                category="fact",
                content="New memory while cleanup waits",
                embedding=[1.0, 0.0],
            ),
        )
    assert not await write_extracted_graph(user, epoch, {}, memory_id=entry.entry_id)
    monkeypatch.setattr(graph_store, "delete_user_data", AsyncMock())
    async with AsyncSessionLocal() as session:
        assert (await delete_all_user_memories(user, session))["external_graph"] == "completed"
    assert not await cleanup_pending(user)
