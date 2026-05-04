"""Unified async database layer for all companion-ai modules.

Provides:
  - Shared SQLAlchemy async engine + session factory
  - Declarative base for all ORM models
  - FastAPI dependency `get_db_session()`
  - Lite-mode SQLite fallback

Usage in modules:
    from shared.database import Base, get_db_session, engine

    class MyModel(Base):
        __tablename__ = "my_table"
        ...

    async with get_db_session() as session:
        ...
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from shared.config import get_settings

logger = structlog.get_logger("shared.database")

settings = get_settings()

# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------

if settings.lite_mode:
    _DATABASE_URL = "sqlite+aiosqlite:///./companion_lite.db"
    _ENGINE_KWARGS: dict[str, Any] = {"echo": False}
else:
    _DATABASE_URL = settings.postgres_url.replace("postgresql://", "postgresql+asyncpg://")
    _ENGINE_KWARGS = {
        "echo": False,
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
    }

engine = create_async_engine(_DATABASE_URL, **_ENGINE_KWARGS)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()

# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session. Use as FastAPI dependency or async context manager."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-compatible dependency alias."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def init_database_schema() -> None:
    """Create all tables registered on the shared Base metadata.

    Modules must import their models before this is called so that
    Base.metadata knows about them.
    """
    from sqlalchemy.sql import text

    async with engine.begin() as conn:
        if not settings.lite_mode:
            # Enable pgvector if available (memory_system will need it)
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception as exc:
                logger.warning("pgvector_extension_failed", error=str(exc))

        await conn.run_sync(Base.metadata.create_all)

    logger.info("database_schema.initialized", lite_mode=settings.lite_mode, url=str(engine.url).replace("://", "://***@"))


async def close_database() -> None:
    """Dispose engine and close all connections."""
    await engine.dispose()
    logger.info("database_engine.disposed")
