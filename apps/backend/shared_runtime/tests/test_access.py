import asyncio
import hashlib
import json
import secrets

import httpx
import pytest
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse

from shared_runtime.access import AccessController, AccessMiddleware, Principal, access_router


def configured(tmp_path, role="user"):
    key = secrets.token_urlsafe(32)
    config = tmp_path / "access.json"
    config.write_text(
        json.dumps(
            {"access_keys": [{"user_id": "alice", "role": role, "sha256": hashlib.sha256(key.encode()).hexdigest()}]}
        ),
        encoding="utf-8",
    )
    return AccessController(config), key


def app_for(controller, *, maximum=16 * 1024 * 1024):
    app = FastAPI()

    async def authorize(_scope, _body, principal):
        return principal

    app.add_middleware(AccessMiddleware, controller=controller, authorize=authorize, max_body_bytes=maximum)
    app.include_router(access_router(controller))

    @app.get("/private")
    async def private():
        return {"private": True}

    return app


async def test_keys_create_short_sessions_and_no_header_can_forge_internal_access(tmp_path):
    controller, key = configured(tmp_path)
    app = app_for(controller)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("198.51.100.3", 123)), base_url="http://test"
    ) as client:
        denied = await client.get("/private", headers={"companion.internal": "true", "X-User-Id": "alice"})
        assert denied.status_code == 401
        login = await client.post("/access/login", json={"access_key": key})
        assert login.status_code == 200
        token = login.json()["session_token"]
        assert token != key and key not in login.text
        client.headers["Authorization"] = "Bearer " + token
        assert (await client.get("/private")).status_code == 200
        assert (await client.get("/access/status")).json()["user_id"] == "alice"
        await client.post("/access/logout")
        assert (await client.get("/private")).status_code == 401


@pytest.mark.parametrize(
    "headers,peer",
    [
        ({}, "203.0.113.1"),
        ({"Origin": "http://evil.invalid"}, "127.0.0.1"),
        ({"X-Forwarded-For": "127.0.0.1"}, "127.0.0.1"),
        ({"Host": "rebound.invalid", "Sec-Fetch-Site": "same-origin"}, "127.0.0.1"),
    ],
)
async def test_local_mode_refuses_network_origins_proxies_and_dns_rebinding(headers, peer):
    app = app_for(AccessController(origins=["http://localhost:5173"]))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(peer, 123)), base_url="http://localhost"
    ) as client:
        assert (await client.get("/private", headers=headers)).status_code == 403
        assert (await client.get("/access/status", headers=headers)).json()["authenticated"] is False


@pytest.mark.parametrize("origin,allowed", [("app://companion", True), ("null", False), ("app://foreign", False)])
async def test_packaged_app_has_an_explicit_origin_without_allowing_generic_file_origins(origin, allowed):
    from shared_runtime.config import Settings

    origins = Settings.model_fields["cors_origins"].default.split(",")
    app = app_for(AccessController(origins=origins))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
                                base_url="http://127.0.0.1") as client:
        response = await client.get("/private", headers={"Origin": origin})
        assert response.status_code == (200 if allowed else 403)


async def test_loopback_stays_available_and_request_body_budget_is_real():
    app = app_for(AccessController(), maximum=8)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/private")).status_code == 200
        assert (await client.post("/private", content=b"123456789")).status_code == 413


@pytest.mark.parametrize("change", ["logout", "config", "role"])
async def test_revocation_drains_an_already_open_stream_instead_of_leaking_future_events(tmp_path, change):
    controller, key = configured(tmp_path)
    app = app_for(controller)
    started, cleaned = asyncio.Event(), asyncio.Event()

    @app.get("/watch")
    async def watch():
        async def stream():
            try:
                started.set()
                yield b"data: first\n\n"
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        return StreamingResponse(stream(), media_type="text/event-stream")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        token = (await client.post("/access/login", json={"access_key": key})).json()["session_token"]
        client.headers["Authorization"] = "Bearer " + token
        reading = asyncio.create_task(client.get("/watch"))
        await asyncio.wait_for(started.wait(), 1)
        if change == "logout":
            await client.post("/access/logout")
        elif change == "config":
            controller.config_file.write_text("malformed", encoding="utf-8")
        else:
            data = json.loads(controller.config_file.read_text(encoding="utf-8"))
            data["access_keys"][0]["role"] = "admin"
            controller.config_file.write_text(json.dumps(data), encoding="utf-8")
        response = await asyncio.wait_for(reading, 2)
        assert response.text == "data: first\n\n" and cleaned.is_set()
        assert not controller._active
        assert (await client.get("/private")).status_code == 401


async def test_websocket_subprotocol_auth_and_live_revocation(tmp_path):
    controller, key = configured(tmp_path)
    token, _ = controller.login(key)
    app = app_for(controller)
    cleaned = asyncio.Event()

    @app.websocket("/socket")
    async def socket(ws: WebSocket):
        await ws.accept()
        try:
            await ws.receive_text()
        finally:
            cleaned.set()

    incoming, outgoing = asyncio.Queue(), asyncio.Queue()
    await incoming.put({"type": "websocket.connect"})
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "scheme": "ws",
        "path": "/socket",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"test")],
        "client": ("203.0.113.2", 123),
        "server": ("test", 80),
        "subprotocols": ["companion.session", token],
    }
    running = asyncio.create_task(app(scope, incoming.get, outgoing.put))
    accepted = await asyncio.wait_for(outgoing.get(), 1)
    assert accepted["type"] == "websocket.accept" and accepted["subprotocol"] == "companion.session"
    assert token not in json.dumps(accepted)
    controller.config_file.write_text("{}", encoding="utf-8")
    closed = await asyncio.wait_for(outgoing.get(), 2)
    assert closed["type"] == "websocket.close" and closed["code"] == 4401
    await running
    assert cleaned.is_set() and not controller._active
