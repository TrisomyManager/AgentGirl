"""PostgreSQL + pgvector schema initialization and ORM models.

Uses shared.database for engine and session management.
Import models here so they register with shared Base.metadata.
"""

import uuid
from datetime import datetime
from typing import AsyncGenerator

import structlog
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, select
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from shared_runtime.database import AsyncSessionLocal, Base, engine
from shared_runtime.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def _uuid_column(**kwargs):
    """Return a UUID-compatible column that works with both PostgreSQL and SQLite."""
    if settings.lite_mode:
        return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), **kwargs)
    return Column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, **kwargs)


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class UserORM(Base):
    """User profile table."""

    __tablename__ = "users"

    id = _uuid_column()
    profile_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class MemoryORM(Base):
    """Long-term memory entries with vector embeddings."""

    __tablename__ = "memories"

    id = _uuid_column()
    user_id = Column(String(64), nullable=False, index=True)
    category = Column(String(32), nullable=False, index=True)
    content = Column(Text, nullable=False)
    importance = Column(Float, default=0.5)
    emotion_tags = Column(JSON, default=list)
    embedding = Column(Text)  # stored as pgvector; handled via raw SQL
    source_turn_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Schema init (pgvector-specific)
# ---------------------------------------------------------------------------


async def init_schema() -> None:
    """Create tables and pgvector extension if not present."""
    from shared.database import init_database_schema

    # Let shared.database create all tables registered on Base.metadata
    await init_database_schema()

    if settings.lite_mode:
        return

    from memory_system.vector_store import resolve_embedding_dim

    embedding_dim = resolve_embedding_dim()

    # pgvector-specific: ensure embedding column is vector type with index
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'memories' AND column_name = 'embedding'
                        AND data_type = 'USER-DEFINED'
                    ) THEN
                        ALTER TABLE memories DROP COLUMN IF EXISTS embedding;
                        ALTER TABLE memories ADD COLUMN embedding vector({embedding_dim});
                    END IF;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_embedding
                ON memories USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_memories_user_created ON memories(user_id, created_at DESC)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC)"
            )
        )
    logger.info("memory_pgvector.initialized")


async def close_engine() -> None:
    """Close engine — delegates to shared.database."""
    from shared.database import close_database
    await close_database()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for DB sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
