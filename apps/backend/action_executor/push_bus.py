"""Process-wide proactive push bus.

When an action runs *asynchronously* — most importantly when a reminder
fires N seconds after it was created — there is no live HTTP turn to
piggy-back the result onto. We need a separate channel that the
frontend can subscribe to.

This module exposes a tiny pub/sub: anyone (e.g. the
``ReminderScheduler``) can publish an event, and the SSE endpoint at
``GET /actions/push`` long-lives a connection per browser tab and
forwards everything on.

In production this would naturally be Redis pub/sub; for Lite Mode we
keep an in-process asyncio.Queue per-subscriber. Both modes share the
same ``ProactivePushBus`` interface so the orchestrator code does not
need to know which is in play.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import Column, Integer, String, Text, func, select
from sqlalchemy.exc import IntegrityError

from shared_runtime.database import AsyncSessionLocal, Base
from shared_runtime.user_lifecycle import assert_user_context

logger = structlog.get_logger("action_executor.push_bus")


@dataclass
class PushEvent:
    """One proactive push to the frontend."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    seq: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "payload": self.payload, "timestamp": self.timestamp}


class PushEventORM(Base):
    """Durable outbox; sequence numbers survive process restarts."""

    __tablename__ = "push_events"
    seq = Column(Integer, primary_key=True, autoincrement=True)
    event_key = Column(String(256), nullable=False, unique=True)
    user_id = Column(String(128), nullable=True, index=True)
    kind = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    timestamp = Column(String(64), nullable=False)


class DurableEventStore:
    def __init__(self, session_factory=None) -> None:
        self.sessions = session_factory or AsyncSessionLocal

    @staticmethod
    def event_key(event: PushEvent) -> str:
        identity = event.payload.get("id") or event.payload.setdefault("event_id", uuid.uuid4().hex)
        occurrence = event.payload.get("fire_at", "")
        return f"{event.kind}:{identity}:{occurrence}"

    async def enqueue(self, session, event: PushEvent) -> None:
        """Join the caller's transaction, so completion and delivery commit together."""
        event.payload.setdefault("event_id", uuid.uuid4().hex)
        row = PushEventORM(
            event_key=self.event_key(event),
            user_id=event.payload.get("user_id"),
            kind=event.kind,
            payload_json=json.dumps(event.payload, ensure_ascii=False),
            timestamp=event.timestamp,
        )
        session.add(row)
        await session.flush()
        event.seq = row.seq

    async def append(self, event: PushEvent) -> bool:
        try:
            async with self.sessions() as session:
                await self.enqueue(session, event)
                await session.commit()
            return True
        except IntegrityError:
            async with self.sessions() as session:
                row = (
                    await session.execute(select(PushEventORM).where(PushEventORM.event_key == self.event_key(event)))
                ).scalar_one_or_none()
                if row is None:
                    raise
                event.seq = row.seq
                event.payload = json.loads(row.payload_json)
            return False

    async def poll_since(self, since_seq: int, user_id: str | None, limit: int = 200) -> dict[str, Any]:
        async with self.sessions() as session:
            latest_query = select(func.max(PushEventORM.seq))
            query = select(PushEventORM).where(PushEventORM.seq > since_seq)
            if user_id is not None:
                query = query.where(PushEventORM.user_id == user_id)
                latest_query = latest_query.where(PushEventORM.user_id == user_id)
            latest = (await session.execute(latest_query)).scalar_one() or 0
            rows = (await session.execute(query.order_by(PushEventORM.seq).limit(limit + 1))).scalars().all()
            has_more = len(rows) > limit
            rows = rows[:limit]
            return {
                "latest_seq": rows[-1].seq if has_more else max(since_seq, latest),
                "has_more": has_more,
                "durable": True,
                "events": [
                    {
                        "seq": row.seq,
                        "kind": row.kind,
                        "payload": json.loads(row.payload_json),
                        "timestamp": row.timestamp,
                    }
                    for row in rows
                ],
            }


class ProactivePushBus:
    """In-process pub/sub: each subscribe() call gets its own queue."""

    def __init__(self, event_store: DurableEventStore | None = None) -> None:
        self.event_store = event_store
        self._subscribers: list[asyncio.Queue[PushEvent]] = []
        self._lock = asyncio.Lock()
        self._seq: int = 0
        self._history: deque[dict[str, Any]] = deque(maxlen=256)

    async def publish(self, event: PushEvent) -> int:
        assert_user_context()
        if self.event_store is not None and event.seq is None and not await self.event_store.append(event):
            return 0
        async with self._lock:
            assert_user_context()
            self._seq = event.seq or self._seq + 1
            seq = self._seq
            self._history.append(
                {
                    "seq": seq,
                    "kind": event.kind,
                    "payload": dict(event.payload),
                    "timestamp": event.timestamp,
                }
            )
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop silently — subscriber is slow, nothing else we can do.
                logger.warning("push_bus.subscriber_full")
        logger.info("push_bus.published", kind=event.kind, subscribers=len(subs))
        return len(subs)

    async def subscribe(self) -> AsyncIterator[PushEvent]:
        """Async generator yielding events for this subscriber until cancelled."""
        q: asyncio.Queue[PushEvent] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._subscribers.append(q)
        logger.info("push_bus.subscribed", total=len(self._subscribers))
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            async with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)
            logger.info("push_bus.unsubscribed", total=len(self._subscribers))

    async def forget_user(self, user_id: str):
        async with self._lock:
            self._history = deque(
                (row for row in self._history if row.get("payload", {}).get("user_id") != user_id), maxlen=256
            )
            for queue in self._subscribers:
                kept = []
                while not queue.empty():
                    event = queue.get_nowait()
                    if event.payload.get("user_id") != user_id:
                        kept.append(event)
                for event in kept:
                    queue.put_nowait(event)

    async def poll_since(self, since_seq: int, user_id: str | None = None) -> dict[str, Any]:
        """Return events with ``seq > since_seq`` for HTTP polling (Cloudflare SSE fallback).

        When *user_id* is provided, only events whose ``payload.user_id`` matches
        are returned. Events without a ``user_id`` in their payload are included
        only when *user_id* is ``None`` (backward-compat mode).
        """
        if self.event_store is not None:
            return await self.event_store.poll_since(since_seq, user_id)
        async with self._lock:
            latest = self._seq
            raw: list[dict[str, Any]] = [dict(e) for e in self._history if e["seq"] > since_seq]
        if user_id is not None:
            raw = [e for e in raw if e.get("payload", {}).get("user_id") == user_id]
        return {"latest_seq": latest, "events": raw}


_push_bus: ProactivePushBus | None = None


def get_proactive_push_bus() -> ProactivePushBus:
    global _push_bus
    if _push_bus is None:
        _push_bus = ProactivePushBus(event_store=DurableEventStore())
    return _push_bus
