import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from device_coordination.command_policy import public_url, valid_payload
from device_coordination.gateway_service import DeviceGatewayService
from device_coordination.registry import DeviceRegistry
from device_coordination.stores.memory import MemoryDeviceAuditStore, MemoryDeviceCommandStore
from shared_contracts.models import DeviceInfo


@pytest.mark.parametrize(
    "url",
    [
        "file:///secret",
        "http://localhost",
        "http://127.0.0.1",
        "http://2130706433",
        "http://0177.0.0.1",
        "http://0x7f000001",
        "https://user:secret@example.com",
        "https://example.com\\@127.0.0.1",
        "https://example.com\n",
    ],
)
def test_remote_url_policy_rejects_unsafe_ambiguous_addresses(url):
    assert not public_url(url)


def test_payload_scope_and_sizes_are_enforced_before_dispatch():
    assert public_url("https://example.com/page?q=test")
    assert valid_payload("show_notification", {"title": "合成测试", "text": "hello"})
    for command, payload in [
        ("ping", {"script": "synthetic"}),
        ("open_url", {"url": []}),
        ("show_notification", {"text": "x" * 2001}),
        ("show_notification", {"text": "hello", "exec": "synthetic"}),
    ]:
        assert not valid_payload(command, payload)


async def gateway():
    registry = DeviceRegistry()
    await registry.register(
        DeviceInfo(
            device_id="test-policy",
            user_id="owner",
            device_type="pc",
            device_name="QA",
            platform="app",
            is_online=True,
            capabilities=["ping"],
            metadata={"device_token": "synthetic-device-token"},
        )
    )
    commands, audit = MemoryDeviceCommandStore(), MemoryDeviceAuditStore()
    transport = MagicMock(subscribe=AsyncMock(), deliver=AsyncMock())
    return DeviceGatewayService(registry, commands, audit, transport), commands, audit


async def test_fast_device_completion_during_push_is_never_regressed_to_delivered(monkeypatch):
    service, commands, audit = await gateway()

    async def fast_client(device_id, frame):
        cid = frame["command"]["command_id"]
        auth = {"command_id": cid, "device_id": device_id, "device_token": "synthetic-device-token"}
        await service.claim_command(**auth)
        await service.mark_running(**auth)
        await service.apply_command_result(**auth, status="succeeded", result={"actual": True}, error=None)
        return True

    monkeypatch.setattr("device_coordination.api.get_ws_push", lambda: fast_client)
    ok, result, error = await service.send_command(user_id="owner", device_id="test-policy", command="ping", payload={})
    assert ok and error is None and result["status"] == "succeeded"
    assert (await commands.get(result["command_id"]))["result"] == {"actual": True}
    events = await audit.list_for_scope(user_id="owner")
    assert [event["action"] for event in reversed(events)] == [
        "created",
        "delivered",
        "claimed",
        "running",
        "succeeded",
    ]


async def test_concurrent_claim_and_run_transitions_allow_only_one_executor(monkeypatch):
    service, commands, _ = await gateway()
    monkeypatch.setattr("device_coordination.api.get_ws_push", lambda: AsyncMock(return_value=False))
    _, row, _ = await service.send_command(user_id="owner", device_id="test-policy", command="ping", payload={})
    original_get = commands.get

    async def compete(operation):
        barrier = asyncio.Event()
        count = 0

        async def synchronized_get(command_id):
            nonlocal count
            snapshot = await original_get(command_id)
            count += 1
            if count == 12:
                barrier.set()
            await barrier.wait()
            return snapshot

        monkeypatch.setattr(commands, "get", synchronized_get)
        results = await asyncio.gather(
            *(
                operation(command_id=row["command_id"], device_id="test-policy", device_token="synthetic-device-token")
                for _ in range(12)
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, dict) for result in results) == 1
        assert sum(isinstance(result, ValueError) for result in results) == 11

    await compete(service.claim_command)
    await compete(service.mark_running)
    monkeypatch.setattr(commands, "get", original_get)
    await service.cancel_command(user_id="owner", command_id=row["command_id"])
    result = await service.apply_command_result(
        command_id=row["command_id"],
        device_id="test-policy",
        device_token="synthetic-device-token",
        status="succeeded",
        result={"late": True},
        error=None,
    )
    assert result["status"] == "cancelled" and result["result"] is None


async def test_unadvertised_capability_is_not_delivered(monkeypatch):
    service, _, _ = await gateway()
    ok, _, error = await service.send_command(
        user_id="owner", device_id="test-policy", command="open_url", payload={"url": "https://example.com"}
    )
    assert not ok and "capability" in error
