"""Tests for device_coordination."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.models import DeviceInfo, DeviceType, Platform
from shared.events import DeviceHeartbeatEvent

from device_coordination.registry import DeviceRegistry, HEARTBEAT_TIMEOUT_SECONDS
from device_coordination.task_dispatcher import TaskDispatcher
from device_coordination.mqtt_client import DeviceMQTTClient


@pytest.fixture
def sample_device() -> DeviceInfo:
    return DeviceInfo(
        device_id="d-001",
        user_id="u-001",
        device_type=DeviceType.MOBILE,
        device_name="Test Phone",
        platform=Platform.APP,
        capabilities=["screen", "notification", "camera"],
        is_online=True,
        last_heartbeat=datetime.utcnow(),
    )


@pytest.fixture
def registry() -> DeviceRegistry:
    return DeviceRegistry()


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_and_get(registry: DeviceRegistry, sample_device: DeviceInfo) -> None:
    with patch("device_coordination.registry.asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={
            "device_id": sample_device.device_id,
            "user_id": sample_device.user_id,
            "device_type": sample_device.device_type.value,
            "device_name": sample_device.device_name,
            "platform": sample_device.platform.value,
            "capabilities": sample_device.capabilities,
            "is_online": True,
            "last_heartbeat": sample_device.last_heartbeat,
            "ip_address": None,
            "metadata": {},
        })
        pool = MagicMock()
        pool._closed = False
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_pool.return_value = pool

        result = await registry.register(sample_device)
        assert result.device_id == sample_device.device_id


@pytest.mark.asyncio
async def test_heartbeat_updates_online_status(registry: DeviceRegistry) -> None:
    with patch("device_coordination.registry.asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={
            "device_id": "d-001",
            "user_id": "u-001",
            "device_type": "mobile",
            "device_name": "Test Phone",
            "platform": "app",
            "capabilities": [],
            "is_online": True,
            "last_heartbeat": datetime.utcnow(),
            "ip_address": "127.0.0.1",
            "metadata": {},
        })
        pool = MagicMock()
        pool._closed = False
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_pool.return_value = pool

        device = await registry.heartbeat("d-001", ip_address="127.0.0.1")
        assert device is not None
        assert device.is_online is True


@pytest.mark.asyncio
async def test_list_for_user(registry: DeviceRegistry) -> None:
    with patch("device_coordination.registry.asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{
            "device_id": "d-001",
            "user_id": "u-001",
            "device_type": "mobile",
            "device_name": "Test Phone",
            "platform": "app",
            "capabilities": ["screen"],
            "is_online": True,
            "last_heartbeat": datetime.utcnow(),
            "ip_address": None,
            "metadata": {},
        }])
        pool = MagicMock()
        pool._closed = False
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_pool.return_value = pool

        devices = await registry.list_for_user("u-001")
        assert len(devices) == 1
        assert devices[0].device_id == "d-001"


@pytest.mark.asyncio
async def test_find_best_for_task(registry: DeviceRegistry, sample_device: DeviceInfo) -> None:
    with patch("device_coordination.registry.asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{
            "device_id": "d-001",
            "user_id": "u-001",
            "device_type": "smart_speaker",
            "device_name": "Living Room Speaker",
            "platform": "app",
            "capabilities": ["speaker", "audio_playback"],
            "is_online": True,
            "last_heartbeat": datetime.utcnow(),
            "ip_address": None,
            "metadata": {},
        }, {
            "device_id": "d-002",
            "user_id": "u-001",
            "device_type": "mobile",
            "device_name": "Test Phone",
            "platform": "app",
            "capabilities": ["screen", "notification"],
            "is_online": True,
            "last_heartbeat": datetime.utcnow(),
            "ip_address": None,
            "metadata": {},
        }])
        pool = MagicMock()
        pool._closed = False
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_pool.return_value = pool

        best = await registry.find_best_for_task("u-001", ["speaker", "audio_playback"])
        assert best is not None
        assert best.device_id == "d-001"


# ---------------------------------------------------------------------------
# TaskDispatcher tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatcher_routes_by_capability(registry: DeviceRegistry, sample_device: DeviceInfo) -> None:
    dispatcher = TaskDispatcher(registry)
    with patch.object(registry, "get", new=AsyncMock(return_value=sample_device)):
        device = await dispatcher.dispatch("u-001", "voice_output", {}, preferred_device_id="d-001")
        assert device is not None
        assert device.device_id == "d-001"


@pytest.mark.asyncio
async def test_dispatcher_broadcast(registry: DeviceRegistry) -> None:
    dispatcher = TaskDispatcher(registry)
    with patch.object(registry, "find_by_capability", new=AsyncMock(return_value=[])):
        with patch.object(registry, "list_for_user", new=AsyncMock(return_value=[])):
            devices = await dispatcher.broadcast("u-001", "notification", {})
            assert devices == []


# ---------------------------------------------------------------------------
# MQTT client tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mqtt_client_lifecycle() -> None:
    client = DeviceMQTTClient()
    mock_client = MagicMock()

    async def fake_run_loop(_settings: Any) -> None:
        client._client = mock_client
        await client._shutdown_event.wait()

    with patch.object(client, "_run_loop", side_effect=fake_run_loop):
        await client.start()
        await asyncio.sleep(0)
        assert client._client is mock_client
        await client.stop()


async def _async_iter(items: list[Any]) -> Any:
    for item in items:
        yield item
