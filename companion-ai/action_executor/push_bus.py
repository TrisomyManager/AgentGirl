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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, Optional

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

    async def publish(self, event: PushEvent) -> int:
        async with self._lock:
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


_push_bus: Optional[ProactivePushBus] = None


def get_proactive_push_bus() -> ProactivePushBus:
    global _push_bus
    if _push_bus is None:
        _push_bus = ProactivePushBus()
    return _push_bus
