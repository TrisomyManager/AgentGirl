"""Redis Pub/Sub producer/consumer wrapper for the companion-ai event bus."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional

import redis.asyncio as aioredis
import structlog

from shared_runtime.config import get_settings
from shared_contracts.events import BaseEvent
from shared_runtime.lite_mode import InMemoryEventBus

logger = structlog.get_logger()

EventHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """Redis Pub/Sub wrapper with async publish and subscribe loops."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        channel_prefix: Optional[str] = None,
    ) -> None:
        self.settings = get_settings()
        self.redis_url = redis_url or self.settings.redis_url
        self.channel_prefix = channel_prefix or self.settings.redis_pubsub_channel_prefix
        self._redis: Optional[aioredis.Redis] = None
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._listen_task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()

    # -- connection -----------------------------------------------------------

    async def connect(self) -> None:
        if self._redis is not None:
            return
        self._redis = aioredis.from_url(
            self.redis_url,
            decode_responses=True,
        )
        self._pubsub = self._redis.pubsub()
        logger.info("event_bus_connected", redis_url=self.redis_url)

    async def disconnect(self) -> None:
        self._stop_event.set()
        if self._listen_task is not None and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        if self._pubsub is not None:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
        logger.info("event_bus_disconnected")

    async def ping(self) -> bool:
        if self._redis is None:
            return False
        try:
            return await self._redis.ping()
        except Exception as exc:
            logger.warning("event_bus_ping_failed", error=str(exc))
            return False

    # -- channel naming -------------------------------------------------------

    def _channel(self, event_type: str) -> str:
        return f"{self.channel_prefix}:{event_type}"

    # -- publish --------------------------------------------------------------

    async def publish(self, event: BaseEvent) -> int:
        if self._redis is None:
            raise RuntimeError("EventBus not connected. Call connect() first.")
        channel = self._channel(event.event_type)
        payload = event.model_dump_json()
        recipients = await self._redis.publish(channel, payload)
        logger.debug(
            "event_published",
            channel=channel,
            event_type=event.event_type,
            event_id=event.event_id,
            recipients=recipients,
        )
        return recipients

    async def publish_raw(self, event_type: str, payload: Dict[str, Any]) -> int:
        if self._redis is None:
            raise RuntimeError("EventBus not connected. Call connect() first.")
        channel = self._channel(event_type)
        payload["event_id"] = payload.get("event_id", str(uuid.uuid4()))
        payload["timestamp"] = payload.get("timestamp", None)
        payload["source_module"] = payload.get("source_module", "core_orchestrator")
        data = json.dumps(payload, default=str)
        recipients = await self._redis.publish(channel, data)
        logger.debug(
            "event_published_raw",
            channel=channel,
            event_type=event_type,
            recipients=recipients,
        )
        return recipients

    # -- subscribe ------------------------------------------------------------

    def on(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def start_listening(self) -> None:
        if self._pubsub is None:
            raise RuntimeError("EventBus not connected. Call connect() first.")
        if not self._handlers:
            logger.info("event_bus_no_handlers")
            return
        channels = [self._channel(et) for et in self._handlers.keys()]
        await self._pubsub.subscribe(*channels)
        logger.info("event_bus_subscribed", channels=channels)
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self) -> None:
        if self._pubsub is None:
            return
        try:
            async for message in self._pubsub.listen():
                if self._stop_event.is_set():
                    break
                if message["type"] != "message":
                    continue
                channel: str = message["channel"]
                data: str = message["data"]
                event_type = channel.removeprefix(f"{self.channel_prefix}:")
                handlers = self._handlers.get(event_type, [])
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError as exc:
                    logger.warning("event_bus_invalid_json", channel=channel, error=str(exc))
                    continue
                logger.debug(
                    "event_received",
                    channel=channel,
                    event_type=event_type,
                    event_id=payload.get("event_id"),
                )
                for handler in handlers:
                    try:
                        await handler(payload)
                    except Exception as exc:
                        logger.exception(
                            "event_handler_error",
                            handler=handler.__name__,
                            event_type=event_type,
                            error=str(exc),
                        )
        except asyncio.CancelledError:
            logger.info("event_bus_listen_cancelled")
            raise
        except Exception as exc:
            logger.error("event_bus_listen_error", error=str(exc))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_event_bus: Optional[EventBus] = None


async def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        settings = get_settings()
        if settings.lite_mode:
            _event_bus = InMemoryEventBus()  # type: ignore[assignment]
            await _event_bus.connect()
        else:
            _event_bus = EventBus()
            await _event_bus.connect()
    return _event_bus


async def shutdown_event_bus() -> None:
    global _event_bus
    if _event_bus is not None:
        await _event_bus.disconnect()
        _event_bus = None
