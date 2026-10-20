"""Unified async database layer for all companion-ai modules (P1-E 物理搬迁完成 / V2.1).

Provides:
  - Shared SQLAlchemy async engine + session factory
  - Declarative base for all ORM models
  - FastAPI dependency ``get_db_session()``
  - Lite-mode SQLite fallback

Originally lived in ``shared/database/``; the legacy package has been removed.

Usage in modules::

    from shared_runtime.database import Base, get_db_session, engine

    class MyModel(Base):
        __tablename__ = "my_table"
        ...

    async with get_db_session() as session:
        ...
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from shared_runtime.config import get_settings
from shared_runtime.log_safety import connection_target

logger = structlog.get_logger("shared_runtime.database")

settings = get_settings()

# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------

if settings.lite_mode:
    _database_file = Path(__file__).resolve().parents[2] / "companion_lite.db"
    _DATABASE_URL = settings.lite_database_url or f"sqlite+aiosqlite:///{_database_file.as_posix()}"
    _ENGINE_KWARGS: dict[str, Any] = {"echo": False, "connect_args": {"timeout": 30}}
else:
    _DATABASE_URL = settings.postgres_url.replace("postgresql://", "postgresql+asyncpg://")
    _ENGINE_KWARGS = {
        "echo": False,
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
    }

engine = create_async_engine(_DATABASE_URL, **_ENGINE_KWARGS)

if settings.lite_mode:

    @event.listens_for(engine.sync_engine, "do_connect")
    def _sqlite_connection_lifecycle(_dialect, _record, _args, kwargs):
        from shared_runtime.database.sqlite_lifecycle import open_sqlite_connection

        kwargs["async_creator_fn"] = open_sqlite_connection

    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite_connection(connection, _record):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


class UserOwnedSession(AsyncSession):
    """Detached work inherits the user generation and cannot restore erased rows."""

    async def execute(self, *args, **kwargs):
        from shared_runtime.user_lifecycle import assert_user_context

        assert_user_context()
        return await super().execute(*args, **kwargs)

    async def flush(self, *args, **kwargs):
        from shared_runtime.user_lifecycle import assert_user_context

        assert_user_context()
        return await super().flush(*args, **kwargs)

    async def commit(self):
        from shared_runtime.user_lifecycle import assert_user_context

        assert_user_context()
        return await super().commit()


AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=UserOwnedSession,
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
            # A missing extension is a failed prerequisite. Swallowing the error
            # leaves PostgreSQL's transaction aborted and hides the actual cause.
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as migration_conn:
        await _ensure_reminder_repeat_column(migration_conn)

    logger.info(
        "database_schema.initialized", lite_mode=settings.lite_mode, target=connection_target(str(engine.url))
    )


async def _ensure_reminder_repeat_column(connection: Any) -> None:
    """Add ``repeat_interval_seconds`` to ``reminders`` if missing (older DB files)."""
    from sqlalchemy import inspect, text

    try:

        def _has_column(sync_conn: Any) -> bool:
            insp = inspect(sync_conn)
            if not insp.has_table("reminders"):
                return True
            cols = {c["name"] for c in insp.get_columns("reminders")}
            return "repeat_interval_seconds" in cols

        has_col = await connection.run_sync(_has_column)
        if has_col:
            return
        await connection.execute(text("ALTER TABLE reminders ADD COLUMN repeat_interval_seconds INTEGER"))
    except Exception as exc:
        logger.warning("reminders_repeat_column_migrate_failed", error=str(exc))


async def close_database() -> None:
    """Dispose engine and close all connections."""
    await engine.dispose()
    if settings.lite_mode:
        from shared_runtime.database.sqlite_lifecycle import drain_sqlite_connections

        await drain_sqlite_connections()
    logger.info("database_engine.disposed")
