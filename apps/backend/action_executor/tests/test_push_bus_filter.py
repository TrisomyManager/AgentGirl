"""Tests for push_bus.poll_since with user_id filtering."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from action_executor.push_bus import PushEvent, ProactivePushBus


@pytest.fixture
def bus() -> ProactivePushBus:
    return ProactivePushBus()


@pytest.mark.asyncio
async def test_poll_since_no_user_id_returns_all_events(bus: ProactivePushBus) -> None:
    await bus.publish(PushEvent(kind="reminder_fired", payload={"id": "1", "user_id": "u1", "text": "a"}))
    await bus.publish(PushEvent(kind="reminder_fired", payload={"id": "2", "user_id": "u2", "text": "b"}))

    result = await bus.poll_since(0)
    assert len(result["events"]) == 2


@pytest.mark.asyncio
async def test_poll_since_with_user_id_filters(bus: ProactivePushBus) -> None:
    await bus.publish(PushEvent(kind="reminder_fired", payload={"id": "1", "user_id": "u1", "text": "a"}))
    await bus.publish(PushEvent(kind="reminder_fired", payload={"id": "2", "user_id": "u2", "text": "b"}))
    await bus.publish(PushEvent(kind="reminder_fired", payload={"id": "3", "user_id": "u1", "text": "c"}))

    result = await bus.poll_since(0, user_id="u1")
    assert len(result["events"]) == 2
    ids = {e["payload"]["id"] for e in result["events"]}
    assert ids == {"1", "3"}


@pytest.mark.asyncio
async def test_poll_since_with_user_id_returns_empty_for_other(bus: ProactivePushBus) -> None:
    await bus.publish(PushEvent(kind="reminder_fired", payload={"id": "1", "user_id": "u1", "text": "a"}))

    result = await bus.poll_since(0, user_id="u2")
    assert len(result["events"]) == 0


@pytest.mark.asyncio
async def test_poll_since_user_id_missing_in_payload_skipped(bus: ProactivePushBus) -> None:
    """Events without a user_id in payload are excluded when filter is set."""
    await bus.publish(PushEvent(kind="system", payload={"msg": "reboot"}))

    result = await bus.poll_since(0, user_id="u1")
    assert len(result["events"]) == 0


@pytest.mark.asyncio
async def test_poll_since_only_after_seq(bus: ProactivePushBus) -> None:
    await bus.publish(PushEvent(kind="reminder_fired", payload={"id": "1", "user_id": "u1", "text": "a"}))
    seq_mid = bus._seq
    await bus.publish(PushEvent(kind="reminder_fired", payload={"id": "2", "user_id": "u1", "text": "b"}))

    result = await bus.poll_since(seq_mid)
    assert len(result["events"]) == 1
    assert result["events"][0]["payload"]["id"] == "2"
