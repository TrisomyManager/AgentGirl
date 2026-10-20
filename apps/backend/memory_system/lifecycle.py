"""Reversible forgetting and retrieval reinforcement; original memories remain intact."""

import asyncio
import math
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, case, delete, select, update
from sqlalchemy.orm import load_only

from memory_system.db import MemoryORM
from shared_contracts.models import MemoryEntry
from shared_runtime.database import Base


class MemoryStateORM(Base):
    __tablename__ = "memory_states"

    memory_id = Column(String(64), primary_key=True)
    user_id = Column(String(128), nullable=False, index=True)
    access_count = Column(Integer, nullable=False, default=0)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    effective_importance = Column(Float, nullable=False, default=0.5)
    dormant_since = Column(DateTime(timezone=True), nullable=True)


class MemoryEpochORM(Base):
    __tablename__ = "memory_user_epochs"
    user_id = Column(String(128), primary_key=True)
    epoch = Column(Integer, nullable=False, default=0)


class StaleMemoryWriteError(RuntimeError):
    """The user cleared data after this operation started."""


async def capture_memory_epoch(user_id: str) -> int:
    from shared_runtime.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        epoch = await memory_epoch(session, user_id)
        await session.commit()
        return epoch


async def memory_epoch(session, user_id: str) -> int:
    if session.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    await session.execute(insert(MemoryEpochORM).values(user_id=user_id, epoch=0).on_conflict_do_nothing())
    return (await session.execute(select(MemoryEpochORM.epoch).where(MemoryEpochORM.user_id == user_id))).scalar_one()


async def lock_memory_epoch(session, user_id: str, *, expected: int | None = None, bump: bool = False) -> bool:
    await memory_epoch(session, user_id)
    statement = update(MemoryEpochORM).where(MemoryEpochORM.user_id == user_id)
    if expected is not None:
        statement = statement.where(MemoryEpochORM.epoch == expected)
    result = await session.execute(statement.values(epoch=MemoryEpochORM.epoch + (1 if bump else 0)))
    return bool(result.rowcount)


def utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def retention(importance: float, idle_days: float, accesses: int) -> float:
    """Time-based decay is deterministic: maintenance frequency cannot accelerate forgetting."""
    half_life_days = 15 + 90 * importance + 30 * math.log1p(max(0, accesses))
    value = importance * 2 ** (-max(0.0, idle_days) / half_life_days)
    if importance >= 0.85:
        value = max(value, importance * 0.6)
    return round(min(1.0, max(0.0, value)), 6)


async def ensure_state(session, entry: MemoryEntry) -> None:
    if session.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    await session.execute(
        insert(MemoryStateORM)
        .values(
            memory_id=entry.entry_id,
            user_id=entry.user_id,
            access_count=0,
            effective_importance=entry.importance,
        )
        .on_conflict_do_nothing(index_elements=["memory_id"])
    )


async def states_for(session, user_id: str, ids: list[str]) -> dict[str, MemoryStateORM]:
    if not ids:
        return {}
    rows = (
        (
            await session.execute(
                select(MemoryStateORM).where(
                    MemoryStateORM.user_id == user_id,
                    MemoryStateORM.memory_id.in_(ids),
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.memory_id: row for row in rows}


async def decorate_entries(session, user_id: str, entries: list[MemoryEntry]) -> list[MemoryEntry]:
    states = await states_for(session, user_id, [entry.entry_id for entry in entries])
    now = datetime.now(UTC)
    for entry in entries:
        state = states.get(entry.entry_id)
        expired = entry.expires_at is not None and utc(entry.expires_at) <= now
        entry.memory_status = "dormant" if expired or (state and state.dormant_since) else "active"
        entry.effective_importance = state.effective_importance if state else entry.importance
        entry.access_count = state.access_count if state else 0
        entry.last_accessed_at = utc(state.last_accessed_at) if state else None
    return entries


async def record_recall(session, user_id: str, entries: list[MemoryEntry]) -> None:
    now = datetime.now(UTC)
    for entry in entries:
        if entry.user_id != user_id:
            continue
        await ensure_state(session, entry)
        await session.execute(
            update(MemoryStateORM)
            .where(
                MemoryStateORM.memory_id == entry.entry_id,
                MemoryStateORM.user_id == user_id,
            )
            .values(
                access_count=MemoryStateORM.access_count + 1,
                last_accessed_at=now,
                dormant_since=None,
                effective_importance=case(
                    (MemoryStateORM.effective_importance < entry.importance, entry.importance),
                    else_=MemoryStateORM.effective_importance,
                ),
            )
        )
        entry.access_count += 1
        entry.last_accessed_at = now
        entry.memory_status = "active"
        entry.effective_importance = max(entry.effective_importance or 0.0, entry.importance)


async def run_forgetting(
    session, user_id: str | None = None, now: datetime | None = None, batch_size: int = 200
) -> dict[str, int]:
    now = utc(now) or datetime.now(UTC)
    query = select(MemoryORM).options(
        load_only(
            MemoryORM.id,
            MemoryORM.user_id,
            MemoryORM.category,
            MemoryORM.importance,
            MemoryORM.created_at,
            MemoryORM.expires_at,
        )
    )
    if user_id is not None:
        query = query.where(MemoryORM.user_id == user_id)
    counts = {"evaluated": 0, "decayed": 0, "newly_dormant": 0, "expired_deleted": 0}
    cursor = None
    batch_size = max(1, min(2000, batch_size))
    while True:
        batch_query = query.where(MemoryORM.id > cursor) if cursor is not None else query
        rows = (await session.execute(batch_query.order_by(MemoryORM.id).limit(batch_size))).scalars().all()
        if not rows:
            break
        for row in rows:
            entry = MemoryEntry(
                entry_id=str(row.id),
                user_id=row.user_id,
                content="",
                category=row.category,
                importance=row.importance,
                created_at=row.created_at,
                expires_at=row.expires_at,
            )
            await ensure_state(session, entry)
            state = await session.get(MemoryStateORM, str(row.id), populate_existing=True)
            last_used = utc(state.last_accessed_at) or utc(row.created_at) or now
            idle_days = max(0.0, (now - last_used).total_seconds() / 86400)
            effective = retention(row.importance, idle_days, state.access_count)
            expired = row.expires_at is not None and utc(row.expires_at) <= now
            if (expired or (idle_days >= 30 and effective < 0.12)) and state.dormant_since is None:
                state.dormant_since = now
                counts["newly_dormant"] += 1
            if abs(state.effective_importance - effective) > 1e-6:
                counts["decayed"] += 1
            state.effective_importance = effective
            counts["evaluated"] += 1
        cursor = rows[-1].id
        await session.commit()
        await asyncio.sleep(0)
    return counts


async def restore_memory(session, user_id: str, memory_id: str, *, commit=True, record_access=True) -> bool:
    row = (
        await session.execute(
            select(MemoryORM).where(
                MemoryORM.user_id == user_id,
                MemoryORM.id == memory_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    entry = MemoryEntry(
        entry_id=str(row.id), user_id=user_id, content=row.content, category=row.category, importance=row.importance
    )
    if record_access:
        await record_recall(session, user_id, [entry])
    row.expires_at = None
    if commit:
        await session.commit()
    return True


async def delete_lifecycle(session, *, user_id: str | None = None, memory_id: str | None = None) -> None:
    statement = delete(MemoryStateORM)
    if user_id is not None:
        statement = statement.where(MemoryStateORM.user_id == user_id)
    if memory_id is not None:
        statement = statement.where(MemoryStateORM.memory_id == memory_id)
    await session.execute(statement)
