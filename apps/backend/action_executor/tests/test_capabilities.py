"""Tests for capabilities catalogue endpoint."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("COMPANION_LITE_MODE", "true")


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Reuse the same app across all tests in this module."""
    import main as _main  # noqa: F401
    from action_executor import handlers as _h  # noqa
    from main import create_app
    app = create_app()
    with TestClient(app) as tc:
        yield tc


def test_capabilities_returns_200(client: TestClient) -> None:
    resp = client.get("/actions/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert "capabilities" in data
    caps = data["capabilities"]
    assert isinstance(caps, list)
    assert len(caps) >= 3, "Expected at least reminder / weather / memory entries"


def test_capabilities_reminder_entry(client: TestClient) -> None:
    resp = client.get("/actions/capabilities")
    caps = resp.json()["capabilities"]
    reminder = next((c for c in caps if c["id"] == "reminder"), None)
    assert reminder is not None, "Expected 'reminder' capability"
    assert reminder["title"] == "提醒我"
    assert reminder["group"] == "生活助手"
    assert len(reminder["examples"]) >= 1
    assert reminder["enabled"] is True
    assert reminder["status"] == "ready"
    assert reminder["requires_config"] is False


def test_capabilities_web_search_needs_config_by_default(client: TestClient) -> None:
    resp = client.get("/actions/capabilities")
    caps = resp.json()["capabilities"]
    search = next((c for c in caps if c["id"] == "web_search"), None)
    assert search is not None
    assert search["requires_config"] is True
    # Without SEARCH_API_KEY, status should be needs_config
    assert search["status"] in ("needs_config", "degraded")


def test_capabilities_memory_entries_present(client: TestClient) -> None:
    resp = client.get("/actions/capabilities")
    caps = resp.json()["capabilities"]
    ids = {c["id"] for c in caps}
    assert "memory_storage" in ids
    assert "memory_recall" in ids


def test_capabilities_no_internal_fields_exposed(client: TestClient) -> None:
    resp = client.get("/actions/capabilities")
    caps = resp.json()["capabilities"]
    forbidden = {"handler", "registry", "params_schema", "ActionDefinition", "stack_trace"}
    for cap in caps:
        for key in cap:
            assert key not in forbidden, f"Field {key!r} should not be exposed to user"


def test_capabilities_every_entry_has_group(client: TestClient) -> None:
    resp = client.get("/actions/capabilities")
    caps = resp.json()["capabilities"]
    for cap in caps:
        assert bool(cap.get("group")), f"Capability {cap.get('id')} missing group"


def test_capabilities_device_entries_present(client: TestClient) -> None:
    resp = client.get("/actions/capabilities")
    caps = resp.json()["capabilities"]
    ids = {c["id"] for c in caps}
    assert "device_list" in ids
    assert "device_notify" in ids
    assert "device_actions" in ids


def test_actions_list_includes_device_handlers(client: TestClient) -> None:
    resp = client.get("/actions/list")
    assert resp.status_code == 200
    actions = resp.json()
    names = {a["name"] for a in actions}
    for n in ("list_devices", "device_ping", "device_notify", "device_open_url"):
        assert n in names, f"Missing action {n!r}"
