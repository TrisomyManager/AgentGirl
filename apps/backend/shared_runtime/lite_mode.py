"""Lite-mode fallbacks for local development without Docker.

P1-D 物理搬迁完成 (V2.1): 原 ``shared.lite_mode`` 的物理实现现在位于本文件;
``shared.lite_mode`` 反向 re-export 兼容老 import.

Replaces Redis, PostgreSQL, and Neo4j with in-memory / SQLite equivalents.
Activated via ``COMPANION_LITE_MODE=true``.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

from shared_contracts.events import BaseEvent

logger = structlog.get_logger(__name__)

EventHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# In-memory EventBus (replaces Redis Pub/Sub)
# ---------------------------------------------------------------------------


class InMemoryEventBus:
    """Asyncio Queue-based event bus for lite mode.

    Handlers are invoked synchronously on *publish* (fire-and-forget
    via ``asyncio.create_task``) so that the caller never blocks.
    """

    def __init__(self, channel_prefix: str = "companion") -> None:
        self.channel_prefix = channel_prefix
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._stop_event = asyncio.Event()

    # -- connection -----------------------------------------------------------

    async def connect(self) -> None:
        logger.info("lite_event_bus_connected")

    async def disconnect(self) -> None:
        self._stop_event.set()
        logger.info("lite_event_bus_disconnected")

    async def ping(self) -> bool:
        return True

    # -- channel naming -------------------------------------------------------

    def _channel(self, event_type: str) -> str:
        return f"{self.channel_prefix}:{event_type}"

    # -- publish --------------------------------------------------------------

    async def publish(self, event: BaseEvent) -> int:
        payload = json.loads(event.model_dump_json())
        return await self.publish_raw(event.event_type, payload)

    async def publish_raw(self, event_type: str, payload: Dict[str, Any]) -> int:
        payload.setdefault("event_id", payload.get("event_id", str(uuid.uuid4())))
        payload.setdefault("timestamp", payload.get("timestamp"))
        payload.setdefault("source_module", payload.get("source_module", "core_orchestrator"))

        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            asyncio.create_task(self._safe_handler(handler, payload))
        return len(handlers)

    async def _safe_handler(self, handler: EventHandler, payload: Dict[str, Any]) -> None:
        try:
            await handler(payload)
        except Exception as exc:
            logger.exception("lite_event_handler_error", error=str(exc))

    # -- subscribe ------------------------------------------------------------

    def on(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def start_listening(self) -> None:
        logger.info("lite_event_bus_listening")

    async def _listen_loop(self) -> None:
        # In lite mode, handlers are invoked synchronously on publish.
        pass


# ---------------------------------------------------------------------------
# In-memory short-term memory (replaces Redis cache)
# ---------------------------------------------------------------------------


class InMemoryShortTermMemory:
    """Dict-based short-term memory for lite mode."""

    def __init__(self, max_entries: int = 100, default_ttl: int = 3600) -> None:
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self._data: Dict[str, str] = {}
        self._session_order: Dict[str, List[str]] = {}

    def _session_key(self, session_id: str) -> str:
        return f"companion:stm:{session_id}"

    def _turn_key(self, session_id: str, turn_id: str) -> str:
        return f"companion:stm:{session_id}:{turn_id}"

    async def add_turn(
        self,
        session_id: str,
        turn_id: str,
        user_message: str,
        assistant_message: str,
        emotion: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        key = self._turn_key(session_id, turn_id)
        data = {
            "turn_id": turn_id,
            "session_id": session_id,
            "user_message": user_message,
            "assistant_message": assistant_message,
            "emotion": emotion.value if emotion else None,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        self._data[key] = json.dumps(data, ensure_ascii=False)
        self._session_order.setdefault(session_id, [])
        self._session_order[session_id].insert(0, turn_id)
        self._session_order[session_id] = self._session_order[session_id][: self.max_entries]
        logger.info("lite_stm.turn_added", session_id=session_id, turn_id=turn_id)

    async def get_session_turns(self, session_id: str) -> List[Dict[str, Any]]:
        turn_ids = self._session_order.get(session_id, [])
        turns: List[Dict[str, Any]] = []
        for turn_id in reversed(turn_ids):
            data = self._data.get(self._turn_key(session_id, turn_id))
            if data:
                turns.append(json.loads(data))
        return turns

    async def get_recent_context(self, session_id: str, last_n: int = 5) -> str:
        turns = await self.get_session_turns(session_id)
        recent = turns[-last_n:] if turns else []
        lines: List[str] = []
        for turn in recent:
            lines.append(f"User: {turn['user_message']}")
            lines.append(f"Assistant: {turn['assistant_message']}")
        return "\n".join(lines)

    async def clear_session(self, session_id: str) -> None:
        turn_ids = self._session_order.get(session_id, [])
        for tid in turn_ids:
            self._data.pop(self._turn_key(session_id, tid), None)
        self._session_order.pop(session_id, None)
        logger.info("lite_stm.session_cleared", session_id=session_id)

    async def set_user_context(self, user_id: str, context: Dict[str, Any], ttl: int = 300) -> None:
        key = f"companion:stm:ctx:{user_id}"
        self._data[key] = json.dumps(context, ensure_ascii=False)

    async def get_user_context(self, user_id: str) -> Optional[Dict[str, Any]]:
        key = f"companion:stm:ctx:{user_id}"
        data = self._data.get(key)
        return json.loads(data) if data else None

    async def delete_user_context(self, user_id: str) -> None:
        key = f"companion:stm:ctx:{user_id}"
        self._data.pop(key, None)


__all__ = ["InMemoryEventBus", "InMemoryShortTermMemory", "EventHandler"]
