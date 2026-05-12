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
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Deque, Dict, List, Optional

import structlog

logger = structlog.get_logger("action_executor.push_bus")


@dataclass
class PushEvent:
    """One proactive push to the frontend."""

    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "payload": self.payload, "timestamp": self.timestamp}


class ProactivePushBus:
    """In-process pub/sub: each subscribe() call gets its own queue."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[PushEvent]] = []
        self._lock = asyncio.Lock()
        self._seq: int = 0
        self._history: Deque[Dict[str, Any]] = deque(maxlen=256)

    async def publish(self, event: PushEvent) -> int:
        async with self._lock:
            self._seq += 1
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

    async def poll_since(self, since_seq: int, user_id: str | None = None) -> Dict[str, Any]:
        """Return events with ``seq > since_seq`` for HTTP polling (Cloudflare SSE fallback).

        When *user_id* is provided, only events whose ``payload.user_id`` matches
        are returned. Events without a ``user_id`` in their payload are included
        only when *user_id* is ``None`` (backward-compat mode).
        """
        async with self._lock:
            latest = self._seq
            raw: List[Dict[str, Any]] = [dict(e) for e in self._history if e["seq"] > since_seq]
        if user_id is not None:
            raw = [e for e in raw if e.get("payload", {}).get("user_id") == user_id]
        return {"latest_seq": latest, "events": raw}


_push_bus: Optional[ProactivePushBus] = None


def get_proactive_push_bus() -> ProactivePushBus:
    global _push_bus
    if _push_bus is None:
        _push_bus = ProactivePushBus()
    return _push_bus
