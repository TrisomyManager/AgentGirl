from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from memory_system.db import Base, MemoryORM
from memory_system.vector_store import search_similar


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        yield db
    await engine.dispose()


async def test_offline_recall_matches_chinese_content_without_embeddings_and_isolates_users(session, monkeypatch):
    from memory_system import vector_store

    monkeypatch.setattr(vector_store, "_resolve_embedding_config", lambda: (None, "", "", 384))
    embed = AsyncMock(side_effect=AssertionError("offline recall must not generate pseudo embeddings"))
    monkeypatch.setattr(vector_store, "_get_embedding", embed)
    session.add_all([
        MemoryORM(id="coffee", user_id="alice", category="preference", content="我喜欢喝不加糖的咖啡", importance=0.8),
        MemoryORM(id="unrelated", user_id="alice", category="fact", content="周末去游泳", importance=1.0),
        MemoryORM(id="other", user_id="bob", category="preference", content="我喜欢喝不加糖的咖啡", importance=1.0),
        MemoryORM(id="expired", user_id="alice", category="event", content="咖啡促销活动", importance=1.0,
                  expires_at=datetime.now(UTC) - timedelta(days=1)),
    ])
    await session.commit()
    entries = await search_similar(session, "alice", "咖啡要加糖吗")
    assert [entry.entry_id for entry in entries] == ["coffee"]
    assert await search_similar(session, "alice", "量子力学") == []
    embed.assert_not_awaited()


async def test_semantic_path_still_works_and_excludes_expired_memories(session, monkeypatch):
    from memory_system import vector_store

    monkeypatch.setattr(vector_store, "_resolve_embedding_config", lambda: ("test-key", "", "", 2))
    monkeypatch.setattr(vector_store, "_get_embedding", AsyncMock(return_value=[1.0, 0.0]))
    session.add_all([
        MemoryORM(id="real", user_id="alice", category="fact", content="a seaside holiday", embedding="[1, 0]"),
        MemoryORM(id="old", user_id="alice", category="fact", content="old trip", embedding="[1, 0]",
                  expires_at=datetime.now(UTC) - timedelta(days=1)),
    ])
    await session.commit()
    assert [e.entry_id for e in await search_similar(session, "alice", "vacation")] == ["real"]
