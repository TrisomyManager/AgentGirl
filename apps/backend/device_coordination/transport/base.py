"""Transport boundary for pushing commands to devices."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class DeviceTransport(ABC):
    """Push-side abstraction; device pull/claim stays on HTTP in Lite Mode."""

    @abstractmethod
    async def deliver(self, command: Dict[str, Any]) -> None:
        """Best-effort delivery of a fully populated command record."""

    @abstractmethod
    async def subscribe(self, device_id: str) -> None:
        """Register interest in a device (e.g. MQTT topic subscription)."""

    @abstractmethod
    async def disconnect(self, device_id: str) -> None:
        """Tear down subscriptions for a device."""

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Lightweight status for ops (connected, mode, last error)."""
