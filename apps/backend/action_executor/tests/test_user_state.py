"""Tests for GET /actions/user_state endpoint."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("COMPANION_LITE_MODE", "true")


@pytest.fixture(scope="module")
def client() -> TestClient:
    import main as _main  # noqa
    from action_executor import handlers as _h  # noqa
    from main import create_app
    app = create_app()
    with TestClient(app) as tc:
        yield tc


def test_user_state_empty_returns_valid_structure(client: TestClient) -> None:
    resp = client.get("/actions/user_state?user_id=test_empty_user")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "test_empty_user"
    assert data["reminders"]["upcoming"] == []
    assert data["reminders"]["recent"] == []
    assert data["tasks"]["open"] == []
    assert data["tasks"]["completed_recent"] == []
    # Proactive rules are capability metadata (not per-user state): with
    # proactive_enabled=True (the default since V2.5), even a fresh user sees
    # the default trigger list so the frontend CapabilityPanel can render
    # toggles (roadmap 1.7). Assert the contract, not emptiness.
    rules = data["proactive"]["rules"]
    rule_ids = {r["id"] for r in rules}
    assert rule_ids == {
        "idle_checkin",
        "morning_greeting",
        "evening_greeting",
        "memory_followup",
    }
    for rule in rules:
        assert isinstance(rule["enabled"], bool)
        assert rule["title"]
        assert rule["schedule"]


async def test_user_state_after_reminder_created(client: TestClient) -> None:
    """Create a reminder via the store directly, then assert it appears in upcoming."""
    from action_executor.reminders import get_reminders_store

    store = get_reminders_store()
    fire_at = datetime.now(UTC) + timedelta(hours=1)
    reminder = await store.add(
        user_id="test_reminder_user",
        text="交材料",
        fire_at=fire_at,
    )

    resp = client.get("/actions/user_state?user_id=test_reminder_user")
    assert resp.status_code == 200
    data = resp.json()

    upcoming = data["reminders"]["upcoming"]
    assert len(upcoming) >= 1
    found = [u for u in upcoming if u["id"] == reminder.id]
    assert len(found) == 1
    assert found[0]["title"] == "交材料"
    assert found[0]["status"] == "pending"


async def test_user_state_fired_reminder_in_recent(client: TestClient) -> None:
    """A manually-fired reminder should appear in recent, not upcoming."""
    from action_executor.reminders import get_reminders_store

    store = get_reminders_store()
    fire_at = datetime.now(UTC) + timedelta(hours=1)
    reminder = await store.add(
        user_id="test_fired_user",
        text="喝水",
        fire_at=fire_at,
    )
    # Manually mark as fired
    await store.mark_fired(reminder.id)

    resp = client.get("/actions/user_state?user_id=test_fired_user")
    assert resp.status_code == 200
    data = resp.json()

    # Should NOT be in upcoming (fired items are excluded)
    upcoming_ids = {u["id"] for u in data["reminders"]["upcoming"]}
    assert reminder.id not in upcoming_ids

    # Should be in recent
    recent_ids = {r["id"] for r in data["reminders"]["recent"]}
    assert reminder.id in recent_ids


async def test_user_state_cancelled_reminder_in_recent(client: TestClient) -> None:
    """A cancelled reminder should appear in recent."""
    from action_executor.reminders import get_reminders_store

    store = get_reminders_store()
    fire_at = datetime.now(UTC) + timedelta(hours=1)
    reminder = await store.add(
        user_id="test_cancel_user",
        text="看邮件",
        fire_at=fire_at,
    )
    await store.cancel(reminder.id)

    resp = client.get("/actions/user_state?user_id=test_cancel_user")
    assert resp.status_code == 200
    data = resp.json()

    upcoming_ids = {u["id"] for u in data["reminders"]["upcoming"]}
    assert reminder.id not in upcoming_ids

    recent = data["reminders"]["recent"]
    found = [r for r in recent if r["id"] == reminder.id]
    assert len(found) == 1
    assert found[0]["status"] == "cancelled"
    assert "cancelled_at" in found[0]


def test_user_state_default_user_id(client: TestClient) -> None:
    """Default user_id should not return 500."""
    resp = client.get("/actions/user_state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "user_001"


def test_user_state_no_internal_leaks(client: TestClient) -> None:
    """Make sure we don't accidentally expose internal table schemas."""
    resp = client.get("/actions/user_state?user_id=test_empty_user")
    data = resp.json()
    sensitive = {"handler", "registry", "ORM", "session", "scheduler"}
    text = str(data)
    for word in sensitive:
        assert word not in text, f"Internal concept {word!r} leaked into user_state response"
