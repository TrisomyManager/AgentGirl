"""HTTP API tests for device gateway (monolithic app, Lite Mode)."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("COMPANION_LITE_MODE", "true")


def _reg_body(
    device_id: str,
    user_id: str,
    *,
    name: str = "Test PC",
) -> dict:
    return {
        "device_id": device_id,
        "user_id": user_id,
        "device_type": "pc",
        "device_name": name,
        "platform": "app",
        "capabilities": ["ping", "show_notification", "open_url", "get_device_status"],
    }


def _register(client: TestClient, device_id: str, user_id: str, *, name: str = "Test PC") -> tuple[str, dict]:
    r = client.post("/device/register", json=_reg_body(device_id, user_id, name=name))
    assert r.status_code == 200
    j = r.json()
    assert j.get("success") is True
    token = j.get("device_token")
    assert token and isinstance(token, str)
    dev = j.get("device") or {}
    assert "device_token" not in (dev.get("metadata") or {})
    return token, dev


@pytest.fixture
def client() -> TestClient:
    from main import create_app

    app = create_app()
    with TestClient(app) as tc:
        yield tc


def test_device_routes_mounted(client: TestClient) -> None:
    uid = f"rt_{uuid.uuid4().hex[:8]}"
    token, _ = _register(client, "pc-route-check", uid)
    assert token


def test_register_returns_token_and_sanitizes_metadata(client: TestClient) -> None:
    uid = f"u_tok_{uuid.uuid4().hex[:8]}"
    token, dev = _register(client, "pc-tok", uid)
    assert len(token) > 20
    assert "device_token" not in (dev.get("metadata") or {})


def test_heartbeat_requires_valid_device_token(client: TestClient) -> None:
    uid = f"u_hb_{uuid.uuid4().hex[:8]}"
    token, _ = _register(client, "pc-hb", uid)
    bad = client.post(
        "/device/heartbeat",
        json={"device_id": "pc-hb", "device_token": "wrong-token"},
    )
    assert bad.status_code == 401
    good = client.post(
        "/device/heartbeat",
        json={"device_id": "pc-hb", "device_token": token},
    )
    assert good.status_code == 200


def test_register_and_list_online(client: TestClient) -> None:
    uid = f"u_list_{uuid.uuid4().hex[:8]}"
    did = "pc-sim-001"
    _register(client, did, uid, name="Sim")
    lst = client.get(f"/device/list/{uid}")
    assert lst.status_code == 200
    data = lst.json()
    assert data.get("success") is True
    devices = data.get("devices", [])
    assert len(devices) >= 1
    match = next((d for d in devices if d["device_id"] == did), None)
    assert match is not None
    assert match.get("is_online") is True


def test_send_command_auto_single_device(client: TestClient) -> None:
    uid = f"u_one_{uuid.uuid4().hex[:8]}"
    _register(client, "pc-one", uid)
    r = client.post(
        "/device/send_command",
        json={"user_id": uid, "command": "ping", "payload": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    cmd = body.get("command", {})
    assert cmd.get("command_id")
    assert cmd.get("user_id") == uid
    assert cmd.get("device_id") == "pc-one"
    assert cmd.get("command") == "ping"
    assert cmd.get("risk_level") == "low"
    assert cmd.get("status") == "delivered"
    assert cmd.get("expires_at")
    assert cmd.get("confirmation_status") == "not_required"


def test_send_command_multi_device_requires_device_id(client: TestClient) -> None:
    uid = f"u_two_{uuid.uuid4().hex[:8]}"
    _register(client, "pc-a", uid, name="A")
    _register(client, "pc-b", uid, name="B")
    r = client.post(
        "/device/send_command",
        json={"user_id": uid, "command": "ping", "payload": {}},
    )
    assert r.status_code == 409
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("error_code") == "multi_device"


def test_claim_next_and_mark_running_and_result(client: TestClient) -> None:
    uid = f"u_cl_{uuid.uuid4().hex[:8]}"
    tok, _ = _register(client, "pc-claim", uid)
    send = client.post(
        "/device/send_command",
        json={"user_id": uid, "command": "ping", "payload": {}, "device_id": "pc-claim"},
    )
    assert send.status_code == 200
    cmd_id = send.json()["command"]["command_id"]

    cl = client.post(
        "/device/commands/claim_next",
        json={"device_id": "pc-claim", "device_token": tok},
    )
    assert cl.status_code == 200
    claimed = cl.json()["command"]
    assert claimed["status"] == "claimed"
    assert claimed["command_id"] == cmd_id

    run = client.post(
        f"/device/commands/{cmd_id}/mark_running",
        json={"device_id": "pc-claim", "device_token": tok},
    )
    assert run.status_code == 200
    assert run.json()["command"]["status"] == "running"

    upd = client.post(
        "/device/command_result",
        json={
            "command_id": cmd_id,
            "device_id": "pc-claim",
            "device_token": tok,
            "status": "succeeded",
            "result": {"pong": True},
        },
    )
    assert upd.status_code == 200
    assert upd.json()["command"]["status"] == "succeeded"

    got = client.get(f"/device/commands/{cmd_id}", params={"user_id": uid})
    assert got.status_code == 200
    assert got.json()["command"]["status"] == "succeeded"


def test_wrong_device_cannot_claim_or_result(client: TestClient) -> None:
    u1 = f"u_x_{uuid.uuid4().hex[:8]}"
    u2 = f"u_y_{uuid.uuid4().hex[:8]}"
    t1, _ = _register(client, "pc-owner", u1)
    t2, _ = _register(client, "pc-intruder", u2)

    send = client.post(
        "/device/send_command",
        json={"user_id": u1, "command": "ping", "payload": {}, "device_id": "pc-owner"},
    )
    assert send.status_code == 200
    cmd_id = send.json()["command"]["command_id"]

    hij = client.post(
        f"/device/commands/{cmd_id}/claim",
        json={"device_id": "pc-intruder", "device_token": t2},
    )
    assert hij.status_code == 403

    res = client.post(
        "/device/command_result",
        json={
            "command_id": cmd_id,
            "device_id": "pc-intruder",
            "device_token": t2,
            "status": "succeeded",
            "result": {},
        },
    )
    assert res.status_code == 403

    # Owner device can still complete the flow
    client.post(
        "/device/commands/claim_next",
        json={"device_id": "pc-owner", "device_token": t1},
    )
    client.post(
        f"/device/commands/{cmd_id}/mark_running",
        json={"device_id": "pc-owner", "device_token": t1},
    )
    fin = client.post(
        "/device/command_result",
        json={
            "command_id": cmd_id,
            "device_id": "pc-owner",
            "device_token": t1,
            "status": "succeeded",
            "result": {"ok": True},
        },
    )
    assert fin.status_code == 200


def test_command_result_idempotent_for_terminal(client: TestClient) -> None:
    uid = f"u_idem_{uuid.uuid4().hex[:8]}"
    tok, _ = _register(client, "pc-idem", uid)
    send = client.post(
        "/device/send_command",
        json={"user_id": uid, "command": "ping", "payload": {}, "device_id": "pc-idem"},
    )
    cmd_id = send.json()["command"]["command_id"]
    client.post("/device/commands/claim_next", json={"device_id": "pc-idem", "device_token": tok})
    client.post(
        f"/device/commands/{cmd_id}/mark_running",
        json={"device_id": "pc-idem", "device_token": tok},
    )
    body = {
        "command_id": cmd_id,
        "device_id": "pc-idem",
        "device_token": tok,
        "status": "succeeded",
        "result": {"a": 1},
    }
    r1 = client.post("/device/command_result", json=body)
    r2 = client.post(
        "/device/command_result",
        json={**body, "status": "failed", "result": {"b": 2}},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["command"]["status"] == "succeeded"
    assert r2.json()["command"]["result"] == {"a": 1}


def test_terminal_command_cannot_mark_running(client: TestClient) -> None:
    uid = f"u_term_{uuid.uuid4().hex[:8]}"
    tok, _ = _register(client, "pc-term", uid)
    send = client.post(
        "/device/send_command",
        json={"user_id": uid, "command": "ping", "payload": {}, "device_id": "pc-term"},
    )
    cmd_id = send.json()["command"]["command_id"]
    client.post("/device/commands/claim_next", json={"device_id": "pc-term", "device_token": tok})
    client.post(
        f"/device/commands/{cmd_id}/mark_running",
        json={"device_id": "pc-term", "device_token": tok},
    )
    client.post(
        "/device/command_result",
        json={
            "command_id": cmd_id,
            "device_id": "pc-term",
            "device_token": tok,
            "status": "succeeded",
            "result": {},
        },
    )
    again = client.post(
        f"/device/commands/{cmd_id}/mark_running",
        json={"device_id": "pc-term", "device_token": tok},
    )
    assert again.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"url": "file:///etc/passwd"},
        {"url": "javascript:alert(1)"},
        {"url": ""},
    ],
)
def test_open_url_rejects_unsafe_or_empty(client: TestClient, payload: dict) -> None:
    uid = f"u_badurl_{uuid.uuid4().hex[:8]}"
    _register(client, "pc-url", uid)
    r = client.post(
        "/device/send_command",
        json={"user_id": uid, "command": "open_url", "payload": payload, "device_id": "pc-url"},
    )
    assert r.status_code == 400


def test_open_url_allows_https(client: TestClient) -> None:
    uid = f"u_okurl_{uuid.uuid4().hex[:8]}"
    _register(client, "pc-ok", uid)
    r = client.post(
        "/device/send_command",
        json={
            "user_id": uid,
            "command": "open_url",
            "payload": {"url": "https://example.com"},
            "device_id": "pc-ok",
        },
    )
    assert r.status_code == 200
    cmd = r.json()["command"]
    assert cmd["command"] == "open_url"
    assert cmd["risk_level"] == "medium"
    assert cmd["confirmation_status"] == "approved"


def test_high_risk_command_blocked(client: TestClient) -> None:
    uid = f"u_hi_{uuid.uuid4().hex[:8]}"
    _register(client, "pc-hi", uid)
    r = client.post(
        "/device/send_command",
        json={"user_id": uid, "command": "remote_shell", "payload": {}, "device_id": "pc-hi"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j.get("success") is False
    assert j.get("error") == "high_risk_blocked"


def test_audit_lists_created_and_claim(client: TestClient) -> None:
    uid = f"u_aud_{uuid.uuid4().hex[:8]}"
    tok, _ = _register(client, "pc-aud", uid)
    client.post(
        "/device/send_command",
        json={"user_id": uid, "command": "ping", "payload": {}, "device_id": "pc-aud"},
    )
    client.post("/device/commands/claim_next", json={"device_id": "pc-aud", "device_token": tok})
    a = client.get("/device/audit", params={"user_id": uid})
    assert a.status_code == 200
    rows = a.json().get("audit") or []
    actions = {x.get("action") for x in rows}
    assert "created" in actions
    assert "claimed" in actions or "delivered" in actions


def test_transport_health(client: TestClient) -> None:
    r = client.get("/device/transport/health")
    assert r.status_code == 200
    assert r.json().get("success") is True
    assert "transport" in r.json()


def test_get_command_requires_user_id(client: TestClient) -> None:
    uid = f"u_gc_{uuid.uuid4().hex[:8]}"
    _register(client, "pc-gc", uid)
    send = client.post(
        "/device/send_command",
        json={"user_id": uid, "command": "ping", "payload": {}, "device_id": "pc-gc"},
    )
    cmd_id = send.json()["command"]["command_id"]
    bad = client.get(f"/device/commands/{cmd_id}")
    assert bad.status_code == 422
    ok = client.get(f"/device/commands/{cmd_id}", params={"user_id": uid})
    assert ok.status_code == 200
