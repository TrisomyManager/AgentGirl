"""Reminder persistence + background polling scheduler.

Schema: ``reminders`` table on the shared ``Base.metadata``:

    id            string PK (uuid4 hex)
    user_id       string indexed
    session_id    string nullable
    text          string — the reminder body the user wrote
    fire_at       datetime UTC — when the reminder should pop
    created_at    datetime UTC
    fired_at      datetime UTC nullable — set when the scheduler fires it
    cancelled_at  datetime UTC nullable — set if user cancels before fire_at

The scheduler polls every ``poll_interval`` seconds; in Lite Mode this
is enough latency-wise. Production (Postgres) deployments could replace
``ReminderScheduler`` with a Celery/cron task, but the public surface
(``due_reminders`` + ``mark_fired``) is the same.

The fired event is published into ``ProactivePushBus`` so any SSE
listener (the frontend bell icon, future Telegram bridge, etc.) can
react.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import structlog
from sqlalchemy import Column, DateTime, String, Text, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import and_

from action_executor.push_bus import PushEvent, get_proactive_push_bus
from shared.database import AsyncSessionLocal, Base

logger = structlog.get_logger("action_executor.reminders")


# ---------------------------------------------------------------------------
# ORM
# ---------------------------------------------------------------------------


class ReminderORM(Base):
    """Reminders persisted to the shared SQLAlchemy engine."""

    __tablename__ = "reminders"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    text = Column(Text, nullable=False)
    fire_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    fired_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)


@dataclass
class Reminder:
    """Public dataclass surfacing what API / handlers care about."""

    id: str
    user_id: str
    session_id: Optional[str]
    text: str
    fire_at: datetime
    created_at: datetime
    fired_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    @classmethod
    def from_orm(cls, row: ReminderORM) -> "Reminder":
        return cls(
            id=row.id,
            user_id=row.user_id,
            session_id=row.session_id,
            text=row.text,
            fire_at=_ensure_aware(row.fire_at),
            created_at=_ensure_aware(row.created_at),
            fired_at=_ensure_aware(row.fired_at) if row.fired_at else None,
            cancelled_at=_ensure_aware(row.cancelled_at) if row.cancelled_at else None,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "text": self.text,
            "fire_at": self.fire_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "fired_at": self.fired_at.isoformat() if self.fired_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "status": self.status,
        }

    @property
    def status(self) -> str:
        if self.cancelled_at:
            return "cancelled"
        if self.fired_at:
            return "fired"
        return "pending"


def _ensure_aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; coerce to UTC-aware for safe comparison."""
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Natural-language "in N minutes" helpers
# ---------------------------------------------------------------------------


_DELAY_PATTERNS = [
    (re.compile(r"(\d+)\s*秒[钟]?(?:后|以后)?"), "seconds"),
    (re.compile(r"(\d+)\s*分[钟]?(?:后|以后)?"), "minutes"),
    (re.compile(r"(\d+)\s*小时(?:后|以后)?"), "hours"),
    (re.compile(r"(\d+)\s*天(?:后|以后)?"), "days"),
    (re.compile(r"(?:in\s+)?(\d+)\s*seconds?"), "seconds"),
    (re.compile(r"(?:in\s+)?(\d+)\s*minutes?"), "minutes"),
    (re.compile(r"(?:in\s+)?(\d+)\s*hours?"), "hours"),
    (re.compile(r"(?:in\s+)?(\d+)\s*days?"), "days"),
]


def parse_relative_delay(text: str) -> Optional[timedelta]:
    """Extract a relative delay like '3 分钟后' from free-form text.

    Returns ``None`` if no recognisable delay phrase is present.
    """
    if not text:
        return None
    for pattern, unit in _DELAY_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                value = int(match.group(1))
            except (ValueError, IndexError):
                continue
            if value <= 0:
                continue
            return timedelta(**{unit: value})
    return None


_REMINDER_PREFIXES = (
    "请帮我提醒一下",
    "请帮我提醒",
    "请提醒我",
    "帮我提醒一下",
    "帮我提醒",
    "提醒一下我",
    "提醒我",
    "提醒",
    "remind me to",
    "remind me",
)


def extract_reminder_body(text: str) -> str:
    """Strip the imperative prefix, the delay phrase, and trailing fluff.

    Heuristic — good enough for the MVP. The remaining text is what we
    want to repeat back to the user when the reminder fires.
    Order is intentional: strip the delay phrase first (it can sit
    before OR after the prefix in Chinese, e.g. "3 分钟后提醒我喝水"),
    then strip the prefix from anywhere it appears, then trim noise.
    """
    if not text:
        return ""
    cleaned = text.strip()

    # 1. Remove the relative-delay clause from anywhere in the string.
    for pattern, _unit in _DELAY_PATTERNS:
        cleaned = pattern.sub("", cleaned).strip(" ，,。.")

    # 2. Remove an imperative prefix if it now sits at the start, OR
    #    anywhere in the body if the delay used to be in front of it.
    lowered = cleaned.lower()
    for prefix in _REMINDER_PREFIXES:
        prefix_lower = prefix.lower()
        idx = lowered.find(prefix_lower)
        if idx == -1:
            continue
        # Only strip if the prefix sits at start or is immediately
        # preceded by whitespace / punctuation — this avoids gobbling
        # "提醒" inside an unrelated word.
        if idx == 0 or cleaned[idx - 1] in " \t，,:：。.；;":
            cleaned = (cleaned[:idx] + cleaned[idx + len(prefix):]).strip(" ，,:：")
            break

    # If the user only supplied a delay (e.g. "5 分钟后" or
    # "3 分钟后提醒我"), return empty so the caller can ask for the
    # reminder body. Returning the original text would trick the caller
    # into thinking the body is the delay clause itself.
    return cleaned


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class RemindersStore:
    """Async CRUD on the reminders table."""

    async def add(
        self,
        user_id: str,
        text: str,
        fire_at: datetime,
        session_id: Optional[str] = None,
    ) -> Reminder:
        """Insert a fresh reminder and return its dataclass form."""
        row = ReminderORM(
            id=uuid.uuid4().hex,
            user_id=user_id,
            session_id=session_id,
            text=text,
            fire_at=_ensure_aware(fire_at),
        )
        async with AsyncSessionLocal() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return Reminder.from_orm(row)

    async def list_for_user(
        self,
        user_id: str,
        include_fired: bool = False,
        include_cancelled: bool = False,
    ) -> List[Reminder]:
        """List reminders for a user, newest fire_at first."""
        async with AsyncSessionLocal() as session:
            stmt = select(ReminderORM).where(ReminderORM.user_id == user_id)
            if not include_fired:
                stmt = stmt.where(ReminderORM.fired_at.is_(None))
            if not include_cancelled:
                stmt = stmt.where(ReminderORM.cancelled_at.is_(None))
            stmt = stmt.order_by(ReminderORM.fire_at.asc())
            rows = (await session.execute(stmt)).scalars().all()
            return [Reminder.from_orm(r) for r in rows]

    async def list_due(self, now: Optional[datetime] = None) -> List[Reminder]:
        """List reminders whose ``fire_at <= now`` and have not fired yet."""
        now = now or datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ReminderORM)
                .where(
                    and_(
                        ReminderORM.fired_at.is_(None),
                        ReminderORM.cancelled_at.is_(None),
                        ReminderORM.fire_at <= now,
                    )
                )
                .order_by(ReminderORM.fire_at.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [Reminder.from_orm(r) for r in rows]

    async def mark_fired(self, reminder_id: str) -> bool:
        async with AsyncSessionLocal() as session:
            stmt = (
                update(ReminderORM)
                .where(
                    ReminderORM.id == reminder_id,
                    ReminderORM.fired_at.is_(None),
                )
                .values(fired_at=datetime.now(timezone.utc))
            )
            result = await session.execute(stmt)
            await session.commit()
            return (result.rowcount or 0) > 0

    async def cancel(self, reminder_id: str, user_id: Optional[str] = None) -> bool:
        async with AsyncSessionLocal() as session:
            where_clauses = [
                ReminderORM.id == reminder_id,
                ReminderORM.cancelled_at.is_(None),
                ReminderORM.fired_at.is_(None),
            ]
            if user_id is not None:
                where_clauses.append(ReminderORM.user_id == user_id)
            stmt = (
                update(ReminderORM)
                .where(and_(*where_clauses))
                .values(cancelled_at=datetime.now(timezone.utc))
            )
            result = await session.execute(stmt)
            await session.commit()
            return (result.rowcount or 0) > 0

    async def get(self, reminder_id: str) -> Optional[Reminder]:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    select(ReminderORM).where(ReminderORM.id == reminder_id)
                )
            ).scalar_one_or_none()
            return Reminder.from_orm(row) if row else None


_store: Optional[RemindersStore] = None


def get_reminders_store() -> RemindersStore:
    global _store
    if _store is None:
        _store = RemindersStore()
    return _store


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class ReminderScheduler:
    """Background task that fires due reminders into the push bus."""

    def __init__(self, poll_interval: float = 1.0) -> None:
        self.poll_interval = poll_interval
        self._task: Optional[asyncio.Task[None]] = None
        self._stopping = asyncio.Event()
        self._store = get_reminders_store()
        self._bus = get_proactive_push_bus()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("reminder_scheduler.started", poll_interval=self.poll_interval)

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, Exception):
                self._task.cancel()
        self._task = None
        logger.info("reminder_scheduler.stopped")

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self._tick_once()
            except Exception as exc:
                logger.warning("reminder_scheduler.tick_failed", error=str(exc))
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self.poll_interval
                )
            except asyncio.TimeoutError:
                pass

    async def _tick_once(self) -> int:
        due = await self._store.list_due()
        if not due:
            return 0
        fired = 0
        for reminder in due:
            ok = await self._store.mark_fired(reminder.id)
            if not ok:
                continue  # someone else fired it
            await self._bus.publish(
                PushEvent(
                    kind="reminder_fired",
                    payload={
                        "id": reminder.id,
                        "user_id": reminder.user_id,
                        "session_id": reminder.session_id,
                        "text": reminder.text,
                        "fire_at": reminder.fire_at.isoformat(),
                    },
                )
            )
            fired += 1
            logger.info("reminder_fired", id=reminder.id, user_id=reminder.user_id)
        return fired


_scheduler: Optional[ReminderScheduler] = None


def get_reminder_scheduler() -> ReminderScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = ReminderScheduler()
    return _scheduler
