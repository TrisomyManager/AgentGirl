"""Reference-host graph write/clear ordering and durable external cleanup receipts."""

import asyncio
from datetime import UTC, datetime
from weakref import WeakValueDictionary

from sqlalchemy import Column, Integer, String, cast, delete, or_, select, union

from memory_system.db import MemoryORM
from memory_system.lifecycle import MemoryEpochORM, MemoryStateORM
from shared_runtime.database import AsyncSessionLocal, Base


class GraphCleanupORM(Base):
    __tablename__ = "memory_graph_cleanup"
    user_id = Column(String(128), primary_key=True)
    epoch = Column(Integer, nullable=False)


class GraphMemoryDeletionORM(Base):
    __tablename__ = "memory_graph_deletions"
    user_id = Column(String(128), primary_key=True)
    memory_id = Column(String(64), primary_key=True)


_locks = WeakValueDictionary()


def graph_lock(user_id):
    key = (asyncio.get_running_loop(), user_id)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


async def cleanup_pending(user_id, *, session=None):
    if session is None:
        async with AsyncSessionLocal() as own_session:
            return await cleanup_pending(user_id, session=own_session)
    if await session.get(GraphCleanupORM, user_id) is not None:
        return True
    return (
        await session.scalar(
            select(GraphMemoryDeletionORM.memory_id).where(GraphMemoryDeletionORM.user_id == user_id).limit(1)
        )
        is not None
    )


async def eligible_memory_ids(session, user_id, ids):
    if not ids:
        return set()
    return set(
        await session.scalars(
            select(cast(MemoryORM.id, String))
            .outerjoin(
                MemoryStateORM,
                cast(MemoryORM.id, String) == MemoryStateORM.memory_id,
            )
            .where(
                MemoryORM.user_id == user_id,
                cast(MemoryORM.id, String).in_(ids),
                or_(MemoryORM.expires_at.is_(None), MemoryORM.expires_at > datetime.now(UTC)),
                MemoryStateORM.dormant_since.is_(None),
            )
        )
    )


async def cleanup_locked(user_id):
    """Caller owns graph_lock; only an actual successful deletion clears a receipt."""
    from memory_system.graph_store import graph_store

    async with AsyncSessionLocal() as session:
        job = await session.get(GraphCleanupORM, user_id)
        epoch = job.epoch if job is not None else None
        ids = list(
            await session.scalars(
                select(GraphMemoryDeletionORM.memory_id)
                .where(GraphMemoryDeletionORM.user_id == user_id)
                .order_by(GraphMemoryDeletionORM.memory_id)
                .limit(32)
            )
        )
        if job is None and not ids:
            return True
    try:
        async with asyncio.timeout(5):
            if epoch is not None:
                await graph_store.delete_user_data(user_id, epoch=epoch)
            else:
                await graph_store.delete_memory_graphs(user_id, ids)
    except Exception:
        return False
    async with AsyncSessionLocal() as session:
        if epoch is not None:
            await session.execute(
                delete(GraphCleanupORM).where(GraphCleanupORM.user_id == user_id, GraphCleanupORM.epoch == epoch)
            )
        statement = delete(GraphMemoryDeletionORM).where(GraphMemoryDeletionORM.user_id == user_id)
        if epoch is None:
            statement = statement.where(GraphMemoryDeletionORM.memory_id.in_(ids))
        await session.execute(statement)
        await session.commit()
    return not await cleanup_pending(user_id)


async def retry_cleanup(after=None):
    async with AsyncSessionLocal() as session:
        pending = union(select(GraphCleanupORM.user_id), select(GraphMemoryDeletionORM.user_id)).subquery()
        query = select(pending.c.user_id).order_by(pending.c.user_id).limit(4)
        if after is not None:
            query = query.where(pending.c.user_id > after)
        users = list(await session.scalars(query))
    for user in users:
        async with graph_lock(user):
            await cleanup_locked(user)
    return users[-1] if users else None


async def cleanup_worker(cursor=None):
    while True:
        await asyncio.sleep(5)
        try:
            cursor = await retry_cleanup(cursor)
        except Exception:
            # Durable receipts remain authoritative; no mutation is replayed.
            cursor = None


async def write_extracted_graph(user_id, expected_epoch, extracted, *, memory_id=None):
    """Serialize the complete derived write against clear, after SQL has committed.

    This is a single-process reference-host lock. Multi-worker graph writers
    require distributed fencing; external SDK writers must honor their own host.
    """
    from memory_system.graph_store import graph_store

    if graph_store._driver is None or memory_id is None:
        return False
    async with graph_lock(user_id):
        async with AsyncSessionLocal() as session:
            epoch = await session.scalar(select(MemoryEpochORM.epoch).where(MemoryEpochORM.user_id == user_id))
            blocked = await cleanup_pending(user_id, session=session)
            exists = await session.scalar(
                select(MemoryORM.id).where(
                    MemoryORM.user_id == user_id,
                    cast(MemoryORM.id, String) == memory_id,
                )
            )
            await session.commit()
        if epoch != expected_epoch or blocked or exists is None:
            return False
        await graph_store.store_memory_graph(user_id, memory_id, extracted, expected_epoch=epoch)
        return True
