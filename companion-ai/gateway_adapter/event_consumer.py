"""Redis Pub/Sub consumer for gateway events.

Listens to:
- `companion:gateway:send`   -> GatewaySendEvent
- `companion:gateway:broadcast` -> GatewayBroadcastEvent

Incoming messages from any platform are converted to TurnStartEvent
and published to Redis on `companion:turn:start`.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, Optional

import redis.asyncio as redis
import structlog

from shared.config import get_settings
from shared.events import GatewaySendEvent, GatewayBroadcastEvent, TurnStartEvent
from shared.models import Platform, UserProfile

logger = structlog.get_logger(__name__)

CHANNEL_SEND = "companion:gateway:send"
CHANNEL_BROADCAST = "companion:gateway:broadcast"
CHANNEL_TURN_START = "companion:turn:start"


class GatewayEventConsumer:
    """Consumes Redis Pub/Sub events and routes them to platform adapters."""

    def __init__(
        self,
        adapter_registry: Dict[Platform, Any],
        session_manager: Any,
    ) -> None:
        self._adapter_registry = adapter_registry
        self._session_manager = session_manager
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._task: Optional[asyncio.Task[None]] = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        settings = get_settings()
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(CHANNEL_SEND, CHANNEL_BROADCAST)
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("event_consumer.started", channels=[CHANNEL_SEND, CHANNEL_BROADCAST])

    async def stop(self) -> None:
        self._shutdown_event.set()
        if self._pubsub:
            await self._pubsub.unsubscribe(CHANNEL_SEND, CHANNEL_BROADCAST)
            await self._pubsub.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.close()
        logger.info("event_consumer.stopped")

    async def _consume_loop(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    continue
                data = json.loads(message["data"])
                channel = message["channel"]
                if channel == CHANNEL_SEND:
                    await self._handle_send(data)
                elif channel == CHANNEL_BROADCAST:
                    await self._handle_broadcast(data)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("event_consumer.handle_error")

    async def _handle_send(self, data: Dict[str, Any]) -> None:
        try:
            event = GatewaySendEvent(**data)
        except Exception as exc:
            logger.warning("event_consumer.invalid_send_event", error=str(exc))
            return
        adapter = self._adapter_registry.get(event.platform)
        if adapter is None:
            logger.warning("event_consumer.no_adapter", platform=event.platform.value)
            return
        try:
            await adapter.send_message(
                user_id=event.user_id,
                content=event.content,
                media={"voice_url": event.voice_url, "action_sequence": event.action_sequence.model_dump() if event.action_sequence else None},
                reply_to_message_id=event.reply_to_message_id,
            )
            logger.info("event_consumer.sent", platform=event.platform.value, user_id=event.user_id)
        except Exception:
            logger.exception("event_consumer.send_failed", platform=event.platform.value, user_id=event.user_id)

    async def _handle_broadcast(self, data: Dict[str, Any]) -> None:
        try:
            event = GatewayBroadcastEvent(**data)
        except Exception as exc:
            logger.warning("event_consumer.invalid_broadcast_event", error=str(exc))
            return
        for platform, adapter in self._adapter_registry.items():
            if platform in event.exclude_platforms:
                continue
            try:
                await adapter.broadcast(event.user_id, event.content)
                logger.info("event_consumer.broadcasted", platform=platform.value, user_id=event.user_id)
            except Exception:
                logger.exception("event_consumer.broadcast_failed", platform=platform.value, user_id=event.user_id)

    # ------------------------------------------------------------------
    # Publishing helpers (used by incoming webhooks / WS)
    # ------------------------------------------------------------------

    async def publish_turn_start(
        self,
        user_id: str,
        platform: Platform,
        content: str,
        session_id: str,
        has_voice: bool = False,
        voice_data_b64: Optional[str] = None,
        has_image: bool = False,
        image_urls: Optional[list[str]] = None,
        device_info: Optional[Any] = None,
    ) -> None:
        """Convert an incoming platform message to TurnStartEvent and publish."""
        if self._redis is None:
            raise RuntimeError("Redis not connected")
        user = UserProfile(user_id=user_id, platform=platform)
        event = TurnStartEvent(
            event_id=str(uuid.uuid4()),
            source_module="gateway_adapter",
            turn_id=str(uuid.uuid4()),
            session_id=session_id,
            user=user,
            user_message=content,
            platform=platform,
            has_voice=has_voice,
            voice_data_b64=voice_data_b64,
            has_image=has_image,
            image_urls=image_urls or [],
            device_info=device_info,
        )
        await self._redis.publish(CHANNEL_TURN_START, event.model_dump_json())
        logger.info("event_consumer.published_turn_start", user_id=user_id, platform=platform.value)
