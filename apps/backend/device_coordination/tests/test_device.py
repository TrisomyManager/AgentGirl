"""Tests for device_coordination."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared_contracts.models import DeviceInfo, DeviceType, Platform

from device_coordination.registry import DeviceRegistry
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


@pytest.fixture
def registry_lite() -> DeviceRegistry:
    """DeviceRegistry with Lite Mode storage (matches default dev / COMPANION_LITE_MODE)."""
    with patch("device_coordination.registry.get_settings") as mock_gs:
        mock_gs.return_value = MagicMock(lite_mode=True)
        yield DeviceRegistry()


# ---------------------------------------------------------------------------
# Registry tests (Lite Mode — in-memory path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_and_get(registry_lite: DeviceRegistry, sample_device: DeviceInfo) -> None:
    result = await registry_lite.register(sample_device)
    assert result.device_id == sample_device.device_id
    got = await registry_lite.get(sample_device.device_id)
    assert got is not None
    assert got.user_id == sample_device.user_id


@pytest.mark.asyncio
async def test_heartbeat_updates_online_status(registry_lite: DeviceRegistry, sample_device: DeviceInfo) -> None:
    await registry_lite.register(sample_device)
    device = await registry_lite.heartbeat(sample_device.device_id, ip_address="127.0.0.1")
    assert device is not None
    assert device.is_online is True
    assert device.ip_address == "127.0.0.1"


@pytest.mark.asyncio
async def test_list_for_user(registry_lite: DeviceRegistry, sample_device: DeviceInfo) -> None:
    await registry_lite.register(sample_device)
    devices = await registry_lite.list_for_user(sample_device.user_id)
    assert len(devices) == 1
    assert devices[0].device_id == sample_device.device_id


@pytest.mark.asyncio
async def test_find_best_for_task(registry_lite: DeviceRegistry) -> None:
    now = datetime.utcnow()
    speaker = DeviceInfo(
        device_id="d-001",
        user_id="u-001",
        device_type=DeviceType.SMART_SPEAKER,
        device_name="Living Room Speaker",
        platform=Platform.APP,
        capabilities=["speaker", "audio_playback"],
        is_online=True,
        last_heartbeat=now,
    )
    phone = DeviceInfo(
        device_id="d-002",
        user_id="u-001",
        device_type=DeviceType.MOBILE,
        device_name="Test Phone",
        platform=Platform.APP,
        capabilities=["screen", "notification"],
        is_online=True,
        last_heartbeat=now,
    )
    await registry_lite.register(speaker)
    await registry_lite.register(phone)
    best = await registry_lite.find_best_for_task("u-001", ["speaker", "audio_playback"])
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
