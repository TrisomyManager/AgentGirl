from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from action_executor.desktop_context import DesktopContextGate, DesktopObservation, ProactivePolicy
from action_executor.proactive_care import ProactiveCareScheduler


def observe(**kwargs):
    return DesktopObservation(user_id="alice", device_id="pc", foreground_app="code.exe", **kwargs)


def policy(**kwargs):
    return ProactivePolicy(desktop_enabled=True, allowed_apps=["code.exe"], dwell_seconds=30, **kwargs)


def test_observation_requires_consent_allowlist_and_real_server_dwell():
    gate = DesktopContextGate()
    gate.update(observe(), now=100)
    assert gate.evaluate("alice", ProactivePolicy(), now=100).reason == "desktop_disabled"
    assert gate.evaluate("alice", policy(), now=100).reason == "dwelling"
    gate.update(observe(), now=120)
    assert gate.evaluate("alice", policy(), now=131).allowed
    assert gate.evaluate("bob", policy(), now=131).reason == "no_context"


@pytest.mark.parametrize("field", ["busy", "fullscreen", "locked", "interacting"])
def test_busy_context_blocks_all_proactive_delivery(field):
    gate = DesktopContextGate()
    gate.update(observe(**{field: True}), now=100)
    assert gate.evaluate("alice", policy(), now=101).reason == field


def test_stale_context_and_changed_app_cannot_trigger():
    gate = DesktopContextGate()
    gate.update(observe(), now=100)
    assert gate.evaluate("alice", policy(), now=200).reason == "stale"
    gate.update(observe(), now=201)
    assert gate.evaluate("alice", policy(), now=202).reason == "dwelling"
    gate.update(observe().model_copy(update={"foreground_app": "private.exe"}), now=210)
    assert gate.evaluate("alice", policy(), now=211).reason == "not_allowlisted"


def test_delivered_context_is_not_repeated_and_other_device_busy_wins():
    gate = DesktopContextGate()
    gate.update(observe(), now=100)
    gate.update(observe(), now=130)
    decision = gate.evaluate("alice", policy(), now=131)
    gate.mark_delivered("alice", decision.signature)
    assert gate.evaluate("alice", policy(), now=132).reason == "already_delivered"
    gate.update(observe(busy=True).model_copy(update={"device_id": "laptop"}), now=133)
    assert gate.evaluate("alice", policy(), now=134).reason == "busy"


async def test_failed_generation_is_not_counted_or_published(monkeypatch):
    scheduler = ProactiveCareScheduler()
    monkeypatch.setattr(scheduler, "_call_orchestrator", AsyncMock(side_effect=RuntimeError("offline")))
    scheduler._store = AsyncMock()
    scheduler._bus = AsyncMock()
    sent = await scheduler._fire_proactive("alice", "idle_checkin", {}, datetime.now(UTC))
    assert sent is False
    scheduler._store.add.assert_not_awaited()
    scheduler._bus.publish.assert_not_awaited()


async def test_remembered_concern_is_not_starved_by_generic_idle_checkin(monkeypatch):
    from datetime import timedelta

    scheduler = ProactiveCareScheduler()
    now = datetime(2026, 10, 23, 12, tzinfo=UTC)
    scheduler._store = AsyncMock()
    scheduler._store.last_sent_for_user.return_value = None
    scheduler._store.count_today.return_value = 0
    scheduler._store.count_trigger_today.return_value = 0
    monkeypatch.setattr("action_executor.proactive_care.read_policy", AsyncMock(return_value=ProactivePolicy()))
    monkeypatch.setattr(scheduler, "_get_user_last_seen", AsyncMock(return_value=now - timedelta(days=6)))
    monkeypatch.setattr(scheduler, "_get_memory_followup_context", AsyncMock(return_value={"memory_content": "面试"}))
    fire = AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler, "_fire_proactive", fire)
    assert await scheduler._evaluate_user("alice", now, False) == 1
    assert fire.await_args.kwargs["trigger_type"] == "memory_followup"
