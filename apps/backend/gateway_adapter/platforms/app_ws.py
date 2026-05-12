"""WebSocket adapter for the standalone App frontend."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional, Set

import structlog
from starlette.websockets import WebSocket

from .base import BasePlatformAdapter

logger = structlog.get_logger(__name__)

OnMessage = Callable[[str, str, Dict[str, Any]], None]


class AppWebSocketAdapter(BasePlatformAdapter):
    """Manages WebSocket connections from the standalone App frontend.

    Each user can have multiple active WebSocket connections.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__("app", config)
        # user_id -> set of WebSocket objects
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._on_message: Optional[OnMessage] = None

    def set_on_message(self, handler: OnMessage) -> None:
        self._on_message = handler

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)
        self._logger.info("app_ws.connected", user_id=user_id, client_count=len(self._connections.get(user_id, set())))

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(user_id, set())
            conns.discard(websocket)
            if not conns:
                self._connections.pop(user_id, None)
        self._logger.info("app_ws.disconnected", user_id=user_id)

    async def receive(self, user_id: str, websocket: WebSocket) -> None:
        """Read messages from a single WebSocket and forward to handler."""
        try:
            while True:
                data = await websocket.receive_text()
                payload = json.loads(data)
                if self._on_message:
                    self._on_message(user_id, payload.get("content", ""), payload)
        except Exception:
            self._logger.debug("app_ws.receive_ended", user_id=user_id)

    async def send_message(
        self,
        user_id: str,
        content: str,
        media: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> Optional[str]:
        message = {
            "type": "message",
            "content": content,
            "media": media or {},
            "reply_to": reply_to_message_id,
        }
        sent = await self._push_to_user(user_id, message)
        return str(sent) if sent else None

    async def broadcast(self, user_id: str, content: str) -> None:
        message = {"type": "broadcast", "content": content}
        await self._push_to_user(user_id, message)

    async def _push_to_user(self, user_id: str, message: Dict[str, Any]) -> int:
        text = json.dumps(message, ensure_ascii=False)
        async with self._lock:
            conns = list(self._connections.get(user_id, set()))
        sent = 0
        dead: List[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(text)
                sent += 1
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.get(user_id, set()).discard(ws)
        self._logger.debug("app_ws.pushed", user_id=user_id, sent=sent)
        return sent

    async def health_check(self) -> bool:
        return True
