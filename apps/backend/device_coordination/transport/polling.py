"""HTTP polling / claim_next — no server push; devices pull via REST."""

from __future__ import annotations

from typing import Any, Dict

from .base import DeviceTransport


class PollingDeviceTransport(DeviceTransport):
    """Lite Mode default: commands become `delivered` in the store; clients use claim_next."""

    async def deliver(self, command: Dict[str, Any]) -> None:
        return None

    async def subscribe(self, device_id: str) -> None:
        return None

    async def disconnect(self, device_id: str) -> None:
        return None

    def health(self) -> Dict[str, Any]:
        return {"mode": "polling", "connected": True}
