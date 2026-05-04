"""MQTT client using aiomqtt with exponential-backoff reconnect."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiomqtt
import structlog

from shared.config import get_settings
from shared.events import DeviceCommandEvent, DeviceHeartbeatEvent
from shared.models import DeviceInfo

logger = structlog.get_logger(__name__)

# Topic templates
TOPIC_HEARTBEAT = "companion/devices/{device_id}/heartbeat"
TOPIC_STATUS = "companion/devices/{device_id}/status"
TOPIC_COMMAND = "companion/devices/{device_id}/command"

OnHeartbeat = Callable[[DeviceHeartbeatEvent], Awaitable[None]]
OnStatus = Callable[[str, Dict[str, Any]], Awaitable[None]]


class DeviceMQTTClient:
    """Async MQTT client for device coordination.

    Subscribes to per-device heartbeat and status topics.
    Publishes commands to individual devices.
    """

    def __init__(
        self,
        on_heartbeat: Optional[OnHeartbeat] = None,
        on_status: Optional[OnStatus] = None,
    ) -> None:
        self._client: Optional[aiomqtt.Client] = None
        self._task: Optional[asyncio.Task[None]] = None
        self._on_heartbeat = on_heartbeat
        self._on_status = on_status
        self._shutdown_event = asyncio.Event()
        self._subscribed_devices: set[str] = set()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        settings = get_settings()
        self._shutdown_event.clear()
        self._task = asyncio.create_task(self._run_loop(settings))
        logger.info("mqtt_client.started", host=settings.mqtt_broker_host, port=settings.mqtt_broker_port)

    async def stop(self) -> None:
        self._shutdown_event.set()
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("mqtt_client.stopped")

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    async def subscribe_device(self, device_id: str) -> None:
        async with self._lock:
            if device_id in self._subscribed_devices:
                return
            self._subscribed_devices.add(device_id)
        if self._client:
            await self._client.subscribe(TOPIC_HEARTBEAT.format(device_id=device_id))
            await self._client.subscribe(TOPIC_STATUS.format(device_id=device_id))
            logger.debug("mqtt_client.subscribed", device_id=device_id)

    async def unsubscribe_device(self, device_id: str) -> None:
        async with self._lock:
            self._subscribed_devices.discard(device_id)
        # aiomqtt does not expose unsubscribe in all versions; best-effort
        logger.debug("mqtt_client.unsubscribed", device_id=device_id)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def send_command(self, device_id: str, command: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self._client is None:
            raise RuntimeError("MQTT client not connected")
        message = {
            "event_id": str(uuid.uuid4()),
            "timestamp": json.dumps(str(asyncio.get_event_loop().time())),
            "source_module": "device_coordination",
            "event_type": "device:command",
            "device_id": device_id,
            "command": command,
            "payload": payload or {},
        }
        topic = TOPIC_COMMAND.format(device_id=device_id)
        await self._client.publish(topic, payload=json.dumps(message, ensure_ascii=False))
        logger.info("mqtt_client.command_published", device_id=device_id, command=command)

    # ------------------------------------------------------------------
    # Internal loop with exponential backoff reconnect
    # ------------------------------------------------------------------

    async def _run_loop(self, settings) -> None:  # type: ignore[no-untyped-def]
        backoff = 1.0
        max_backoff = 60.0

        while not self._shutdown_event.is_set():
            try:
                async with aiomqtt.Client(
                    hostname=settings.mqtt_broker_host,
                    port=settings.mqtt_broker_port,
                    username=settings.mqtt_username,
                    password=settings.mqtt_password,
                    identifier=f"device_coordination_{uuid.uuid4().hex[:8]}",
                ) as client:
                    self._client = client
                    # Re-subscribe known devices
                    async with self._lock:
                        for device_id in list(self._subscribed_devices):
                            await client.subscribe(TOPIC_HEARTBEAT.format(device_id=device_id))
                            await client.subscribe(TOPIC_STATUS.format(device_id=device_id))
                    logger.info("mqtt_client.connected")
                    backoff = 1.0

                    async for message in client.messages:
                        if self._shutdown_event.is_set():
                            break
                        try:
                            await self._handle_message(message)
                        except Exception:
                            logger.exception("mqtt_client.handle_message_error")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("mqtt_client.connection_error", error=str(exc), backoff=backoff)
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, max_backoff)

    async def _handle_message(self, message: aiomqtt.Message) -> None:
        topic: str = str(message.topic)
        payload = json.loads(message.payload.decode("utf-8"))
        parts = topic.split("/")
        if len(parts) < 4:
            return
        device_id = parts[2]
        sub_topic = parts[3]

        if sub_topic == "heartbeat":
            device_info = DeviceInfo(**payload.get("device_info", {}))
            event = DeviceHeartbeatEvent(
                event_id=payload.get("event_id", str(uuid.uuid4())),
                timestamp=device_info.last_heartbeat,
                source_module="device_coordination",
                device_info=device_info,
            )
            if self._on_heartbeat:
                await self._on_heartbeat(event)
        elif sub_topic == "status":
            if self._on_status:
                await self._on_status(device_id, payload)
