"""Tests for gateway_adapter."""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared_contracts.models import Platform, UserProfile
from shared_contracts.events import GatewaySendEvent, GatewayBroadcastEvent

from gateway_adapter.session_manager import SessionManager, SessionInfo
from gateway_adapter.event_consumer import GatewayEventConsumer
from gateway_adapter.platforms import AppWebSocketAdapter, TelegramAdapter


# ---------------------------------------------------------------------------
# Session Manager tests
# ---------------------------------------------------------------------------

def test_session_manager_creates_session() -> None:
    sm = SessionManager()
    session = sm.get_or_create("u-001", Platform.TELEGRAM, "tg-123")
    assert session.user_id == "u-001"
    assert session.platform == Platform.TELEGRAM
    assert session.platform_session_id == "tg-123"
    assert session.companion_session_id is not None


def test_session_manager_continuity() -> None:
    sm = SessionManager()
    s1 = sm.get_or_create("u-001", Platform.TELEGRAM, "tg-123")
    s2 = sm.get_or_create("u-001", Platform.DISCORD, "dc-456")
    assert s1.companion_session_id == s2.companion_session_id


def test_session_manager_list_for_user() -> None:
    sm = SessionManager()
    sm.get_or_create("u-001", Platform.TELEGRAM, "tg-123")
    sm.get_or_create("u-001", Platform.APP, "ws-789")
    sessions = sm.list_for_user("u-001")
    assert len(sessions) == 2


def test_session_manager_remove() -> None:
    sm = SessionManager()
    sm.get_or_create("u-001", Platform.TELEGRAM, "tg-123")
    sm.remove("u-001", Platform.TELEGRAM, "tg-123")
    assert sm.get("u-001", Platform.TELEGRAM, "tg-123") is None


# ---------------------------------------------------------------------------
# Event Consumer tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_consumer_handle_send() -> None:
    adapter = MagicMock(spec=TelegramAdapter)
    adapter.send_message = AsyncMock(return_value="msg-123")

    consumer = GatewayEventConsumer(
        adapter_registry={Platform.TELEGRAM: adapter},
        session_manager=SessionManager(),
    )

    event = GatewaySendEvent(
        event_id="e-001",
        source_module="test",
        user_id="u-001",
        platform=Platform.TELEGRAM,
        content="Hello",
    )
    await consumer._handle_send(event.model_dump())
    adapter.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_consumer_handle_broadcast() -> None:
    adapter = MagicMock(spec=TelegramAdapter)
    adapter.broadcast = AsyncMock()

    consumer = GatewayEventConsumer(
        adapter_registry={Platform.TELEGRAM: adapter},
        session_manager=SessionManager(),
    )

    event = GatewayBroadcastEvent(
        event_id="e-002",
        source_module="test",
        user_id="u-001",
        content="Broadcast",
    )
    await consumer._handle_broadcast(event.model_dump())
    adapter.broadcast.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_consumer_publish_turn_start() -> None:
    with patch("gateway_adapter.event_consumer.redis.from_url") as mock_redis_cls:
        mock_redis = AsyncMock()
        mock_redis_cls.return_value = mock_redis

        consumer = GatewayEventConsumer(
            adapter_registry={},
            session_manager=SessionManager(),
        )
        consumer._redis = mock_redis

        await consumer.publish_turn_start(
            user_id="u-001",
            platform=Platform.APP,
            content="Hi",
            session_id="s-001",
        )
        mock_redis.publish.assert_awaited_once()
        channel, payload = mock_redis.publish.call_args[0]
        assert channel == "companion:turn:start"
        data = json.loads(payload)
        assert data["user"]["user_id"] == "u-001"
        assert data["event_type"] == "turn:start"


# ---------------------------------------------------------------------------
# App WebSocket Adapter tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_app_ws_connect_and_send() -> None:
    adapter = AppWebSocketAdapter({})
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()

    await adapter.connect("u-001", ws)
    ws.accept.assert_awaited_once()

    await adapter.send_message("u-001", "Hello")
    ws.send_text.assert_awaited_once()
    sent = json.loads(ws.send_text.call_args[0][0])
    assert sent["content"] == "Hello"
