"""WebSocket push transport — skeleton for a future Windows / PC long-lived client.

TODO: Maintain device_id -> WebSocket session mapping (e.g. in Starlette/FastAPI
router or a shared connection manager). On ``deliver``, serialize the full
command dict (command_id, payload, risk_level, expires_at, confirmation_status)
and send a typed message. Implement ``subscribe``/``disconnect`` as session
registry hooks. Lite Mode can keep using ``PollingDeviceTransport`` until this
is wired.
"""

from __future__ import annotations

from typing import Any, Dict


class WebSocketDeviceTransport:
    async def deliver(self, command: Dict[str, Any]) -> None:
        raise NotImplementedError("TODO: WebSocket device sessions are not enabled yet")

    async def subscribe(self, device_id: str) -> None:
        return None

    async def disconnect(self, device_id: str) -> None:
        return None

    def health(self) -> Dict[str, Any]:
        return {"mode": "websocket", "connected": False, "hint": "not_implemented"}
