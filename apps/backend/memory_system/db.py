"""PostgreSQL + pgvector schema initialization and ORM models.

Uses shared_runtime.database for engine and session management.
Import models here so they register with shared Base.metadata.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

import structlog
from sqlalchemy import JSON, Column, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from shared_runtime.config import get_settings
from shared_runtime.database import AsyncSessionLocal, Base, engine

logger = structlog.get_logger(__name__)
settings = get_settings()


def _uuid_column(**kwargs):
    """Return a UUID-compatible column that works with both PostgreSQL and SQLite."""
    if settings.lite_mode:
        return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), **kwargs)
    return Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, **kwargs)


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
    from shared_runtime.database import init_database_schema

    # Let shared_runtime.database create all tables registered on Base.metadata
    await init_database_schema()

    if settings.lite_mode:
        return

    from memory_system.vector_store import resolve_embedding_dim

    embedding_dim = resolve_embedding_dim()

    # Conversion is transactional and preserves values. Invalid legacy values
    # or incompatible dimensions must fail startup instead of dropping data.
    async with engine.begin() as conn:
        from memory_system.postgres_schema import migration_plan

        pending = await migration_plan(conn, embedding_dim)
        if any("emotion_tags" in statement or "DROP NOT NULL" in statement for statement in pending):
            raise RuntimeError("Historical memory schema requires tools/migrate_postgres.py; back up before --apply")
        if not 1 <= embedding_dim <= 2000:
            raise ValueError("Embedding dimension must be between 1 and 2000 for vector indexes")
        column_type = await conn.scalar(text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'memories'::regclass AND attname = 'embedding' AND NOT attisdropped"
        ))
        expected_type = f"vector({embedding_dim})"
        if column_type in {"text", "character varying", "vector"}:
            await conn.execute(text(
                f"ALTER TABLE memories ALTER COLUMN embedding TYPE {expected_type} "
                f"USING embedding::{expected_type}"
            ))
        elif column_type != expected_type:
            raise RuntimeError("Memory embedding schema differs from configured dimension; explicit migration required")
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_embedding_hnsw
                ON memories USING hnsw (embedding vector_cosine_ops);
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
    """Close engine — delegates to shared_runtime.database."""
    from shared_runtime.database import close_database
    await close_database()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for DB sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
