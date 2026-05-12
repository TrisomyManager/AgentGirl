"""MQTT push transport — publishes the full command envelope to the device topic."""

from __future__ import annotations

from typing import Any, Dict, Optional

from device_coordination.mqtt_client import DeviceMQTTClient

from .base import DeviceTransport


class MqttDeviceTransport(DeviceTransport):
    """Bridges the gateway to ``DeviceMQTTClient`` with a structured payload.

    The published JSON includes command_id, command, payload, risk_level,
    expires_at, confirmation fields, and status so PC/mobile clients do not
    rely on out-of-band context.
    """

    def __init__(self, mqtt: DeviceMQTTClient) -> None:
        self._mqtt = mqtt
        self._last_error: Optional[str] = None

    async def deliver(self, command: Dict[str, Any]) -> None:
        device_id = command["device_id"]
        await self._mqtt.subscribe_device(device_id)
        try:
            await self._mqtt.publish_command_envelope(device_id, command)
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            raise

    async def subscribe(self, device_id: str) -> None:
        await self._mqtt.subscribe_device(device_id)

    async def disconnect(self, device_id: str) -> None:
        await self._mqtt.unsubscribe_device(device_id)

    def health(self) -> Dict[str, Any]:
        return {
            "mode": "mqtt",
            "connected": self._mqtt.is_connected,
            "last_error": self._last_error,
        }
