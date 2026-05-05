"""pytest tests for the memory_system module."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text

from shared.models import EmotionTag, MemoryCategory, MemoryEntry

from memory_system.db import Base, MemoryORM, UserORM
from memory_system.short_term import ShortTermMemory
from memory_system.vector_store import store_memory

# Use an in-memory SQLite for unit tests (async)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def sample_memory_entry():
    return MemoryEntry(
        entry_id=str(uuid.uuid4()),
        user_id="user_123",
        category=MemoryCategory.FACT,
        content="User likes rainy days and hot chocolate.",
        importance=0.8,
        emotion_tags=[EmotionTag.HAPPY, EmotionTag.CALM],
        source_turn_id="turn_001",
        created_at=datetime.utcnow(),
        expires_at=None,
    )


class TestDatabaseSchema:
    async def test_user_orm_create(self, db_session):
        user = UserORM(profile_json={"name": "Alice"})
        db_session.add(user)
        await db_session.commit()
        assert user.id is not None
        assert user.profile_json["name"] == "Alice"

    async def test_memory_orm_create(self, db_session):
        mem = MemoryORM(
            user_id="user_123",
            category="fact",
            content="Test memory",
            importance=0.5,
            emotion_tags=["happy"],
            source_turn_id="turn_001",
        )
        db_session.add(mem)
        await db_session.commit()
        assert mem.id is not None


class TestVectorStore:
    @patch("memory_system.vector_store._get_embedding")
    async def test_store_memory(self, mock_embedding, db_session, sample_memory_entry):
        mock_embedding.return_value = [0.1] * 1536
        result = await store_memory(db_session, sample_memory_entry)
        assert result.entry_id is not None
        assert result.embedding is not None

    @patch("memory_system.vector_store._get_embedding")
    async def test_search_similar(self, mock_embedding, db_session, sample_memory_entry):
        mock_embedding.return_value = [0.1] * 1536
        await store_memory(db_session, sample_memory_entry)

        from memory_system.vector_store import search_similar

        mock_embedding.return_value = [0.1] * 1536
        results = await search_similar(db_session, "user_123", "rainy days", top_k=5)
        assert len(results) >= 1
        assert results[0].user_id == "user_123"


class TestShortTermMemory:
    @pytest.fixture
    def stm(self, monkeypatch):
        # Force the redis-backed code path even when conftest enables lite_mode.
        import memory_system.short_term as st_mod
        monkeypatch.setattr(st_mod.settings, "lite_mode", False, raising=False)
        s = ShortTermMemory(max_entries=10, default_ttl=3600)
        s._backend = None
        return s

    @patch("memory_system.short_term._get_redis")
    async def test_add_and_get_turns(self, mock_redis_factory, stm):
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis_factory.return_value = mock_redis
        stm._redis = mock_redis

        await stm.add_turn(
            session_id="sess_1",
            turn_id="turn_1",
            user_message="Hello",
            assistant_message="Hi there!",
            emotion=EmotionTag.HAPPY,
        )

        mock_redis.pipeline.assert_called_once()
        mock_pipe.execute.assert_awaited_once()

    @patch("memory_system.short_term._get_redis")
    async def test_get_recent_context(self, mock_redis_factory, stm):
        mock_redis = AsyncMock()
        mock_redis_factory.return_value = mock_redis
        stm._redis = mock_redis

        mock_redis.lrange.return_value = ["turn_1"]
        mock_redis.get.return_value = (
            '{"user_message":"Hello","assistant_message":"Hi!"}'
        )

        ctx = await stm.get_recent_context("sess_1", last_n=1)
        assert "User: Hello" in ctx
        assert "Assistant: Hi!" in ctx


class TestGraphStore:
    @patch("memory_system.graph_store.graph_store._driver")
    async def test_merge_user(self, mock_driver):
        from memory_system.graph_store import graph_store

        mock_session = AsyncMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

        await graph_store.merge_user("user_123", {"name": "Alice"})
        mock_session.run.assert_awaited_once()


class TestPipeline:
    def test_stage1_raw_archive(self):
        from memory_system.pipeline import stage1_raw_archive

        turn = {"turn_id": "t1", "user_id": "u1", "user_message": "hi"}
        result = stage1_raw_archive.run(turn)
        assert "archive_id" in result
        assert "archived_at" in result

    @patch("memory_system.pipeline._llm_chat")
    def test_stage2_entity_extraction(self, mock_llm):
        from memory_system.pipeline import stage2_entity_extraction

        mock_llm.return_value = (
            '{"entities":[{"name":"Alice","type":"person","properties":{}}],'
            '"relationships":[],"events":[],"preferences":[],"emotions":[]}'
        )
        turn = {
            "turn_id": "t1",
            "user_id": "u1",
            "user_message": "My name is Alice.",
            "assistant_message": "Nice to meet you, Alice!",
        }
        result = stage2_entity_extraction.run(turn)
        assert "extracted" in result
        assert len(result["extracted"]["entities"]) == 1

    @patch("memory_system.pipeline._llm_chat")
    def test_stage3_importance_scoring(self, mock_llm):
        from memory_system.pipeline import stage3_importance_scoring

        mock_llm.return_value = (
            '{"importance":0.85,"reason":"Personal disclosure","category":"fact"}'
        )
        turn = {"turn_id": "t1", "user_id": "u1", "user_message": "I love you."}
        result = stage3_importance_scoring.run(turn)
        assert result["importance"] == 0.85
        assert result["suggested_category"] == "fact"

    def test_stage4_conflict_resolution(self):
        from memory_system.pipeline import stage4_conflict_resolution

        turn = {
            "turn_id": "t1",
            "user_id": "u1",
            "extracted": {
                "entities": [
                    {"name": "Alice", "type": "person"},
                    {"name": "alice", "type": "person"},
                ]
            },
        }
        result = stage4_conflict_resolution.run(turn)
        assert result["conflicts_resolved"] == 1
        assert len(result["extracted"]["entities"]) == 1

    @patch("memory_system.pipeline.AsyncSessionLocal")
    @patch("memory_system.pipeline.store_memory")
    @patch("memory_system.pipeline.graph_store")
    async def test_stage5_long_term_storage(self, mock_graph, mock_store, mock_session_cls):
        from memory_system.pipeline import stage5_long_term_storage

        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_graph.merge_user = AsyncMock()
        mock_graph.merge_entity = AsyncMock()
        mock_graph.merge_relationship = AsyncMock()
        mock_graph.log_event = AsyncMock()
        mock_graph.add_preference = AsyncMock()
        mock_graph.add_emotion = AsyncMock()

        turn = {
            "turn_id": "t1",
            "user_id": "u1",
            "user_message": "I like pizza.",
            "assistant_message": "Great!",
            "importance": 0.7,
            "suggested_category": "preference",
            "extracted": {
                "entities": [{"name": "pizza", "type": "thing"}],
                "relationships": [],
                "events": [],
                "preferences": [{"key": "food", "value": "pizza", "strength": 0.8}],
                "emotions": [],
            },
        }
        result = stage5_long_term_storage.run(turn)
        assert "memory_entry_id" in result


class TestRecall:
    @patch("memory_system.recall.search_similar")
    @patch("memory_system.recall.graph_store")
    @patch("memory_system.recall._fetch_relationship_metrics")
    async def test_recall_memory(self, mock_metrics, mock_graph, mock_search, db_session):
        from memory_system.recall import recall_memory

        mock_search.return_value = [
            MemoryEntry(
                entry_id="m1",
                user_id="u1",
                category=MemoryCategory.FACT,
                content="User likes cats.",
                importance=0.8,
            )
        ]
        mock_graph.get_user_facts = AsyncMock(return_value=["User has a cat named Mimi."])
        mock_metrics.return_value = None

        result = await recall_memory(
            session=db_session,
            user_id="u1",
            query="pets",
            top_k=5,
        )
        assert len(result.entries) == 1
        assert len(result.graph_facts) == 1
