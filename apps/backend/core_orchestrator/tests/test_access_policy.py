import asyncio
import hashlib
import json
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from memory_system.session_store import PersistentSessionMemory
from shared_runtime.database import init_database_schema


@pytest.fixture
async def secure_host(tmp_path, monkeypatch):
    import main
    from core_orchestrator import api

    keys = {name: secrets.token_urlsafe(32) for name in ("alice", "bob", "operator")}
    path = tmp_path / "access.json"
    path.write_text(
        json.dumps(
            {
                "access_keys": [
                    {
                        "user_id": name,
                        "role": "admin" if name == "operator" else "user",
                        "sha256": hashlib.sha256(key.encode()).hexdigest(),
                    }
                    for name, key in keys.items()
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(main.settings, "access_config_file", str(path))
    app = main.create_app()
    await init_database_schema()

    async def turn(context):
        return {
            "turn_id": context.turn_id,
            "session_id": context.session_id,
            "user_id": context.user.user_id,
            "assistant_message": "test response",
        }

    monkeypatch.setattr(api, "get_orchestrator", AsyncMock(return_value=SimpleNamespace(process_turn=turn)))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("198.51.100.1", 123)), base_url="http://test"
    ) as client:
        yield app, client, keys
    from core_orchestrator.http_client import close_all

    await close_all()


async def test_reference_host_binds_users_sessions_and_admin_operations(secure_host):
    _, client, keys = secure_host
    assert (await client.get("/memory/user/alice/list")).status_code == 401
    client.headers["Authorization"] = "Bearer " + keys["alice"]
    assert (await client.get("/memory/user/alice/list")).status_code == 200
    assert (await client.get("/memory/user/bob/list")).status_code == 403
    assert (await client.get("/orchestrator/settings/llm")).status_code == 403
    assert (await client.post("/actions/dispatch", json={"name": "get_time"})).status_code == 403
    session_id = "access-" + uuid4().hex
    payload = {"user": {"user_id": "alice"}, "session_id": session_id, "user_message": "hello"}
    assert (await client.post("/orchestrator/turn", json=payload)).status_code == 200
    payload["user"]["user_id"] = "bob"
    assert (await client.post("/orchestrator/turn", json=payload)).status_code == 403
    client.headers["Authorization"] = "Bearer " + keys["bob"]
    assert (await client.post("/orchestrator/turn", json=payload)).status_code == 404
    assert (await client.get(f"/memory/working/{session_id}")).status_code == 404


async def test_nested_router_prefix_keeps_path_ownership_checks(secure_host):
    from fastapi import APIRouter

    app, client, keys = secure_host
    inner, outer = APIRouter(), APIRouter()

    @inner.get("/users/{user_id}")
    async def owned(user_id: str):
        return {"user_id": user_id}

    outer.include_router(inner, prefix="/level")
    app.include_router(outer, prefix="/compat")
    client.headers["Authorization"] = "Bearer " + keys["alice"]
    assert (await client.get("/compat/level/users/alice")).status_code == 200
    assert (await client.get("/compat/level/users/bob")).status_code == 403
    client.headers["Authorization"] = "Bearer " + keys["operator"]
    assert (await client.get("/orchestrator/settings/llm")).status_code == 200


async def test_admin_management_and_catalog_require_role_and_separate_host_install_grant(secure_host, tmp_path, monkeypatch):
    from action_executor.plugins import plugin_manager
    from shared_runtime.config import get_settings

    app, client, keys = secure_host
    monkeypatch.setattr(plugin_manager, "directory", tmp_path)
    monkeypatch.setattr(plugin_manager, "config_file", None)
    monkeypatch.setattr(get_settings(), "plugin_install_enabled", False)
    client.headers["Authorization"] = "Bearer " + keys["alice"]
    assert (await client.get("/orchestrator/admin/overview")).status_code == 403
    assert (await client.get("/actions/plugins/catalog")).status_code == 403
    assert (await client.post("/actions/plugins/catalog/text_tools/install", json={"sha256": "0" * 64})).status_code == 403
    client.headers["Authorization"] = "Bearer " + keys["operator"]
    app.state.startup_modules = {"database": "ready"}
    overview = (await client.get("/orchestrator/admin/overview")).json()
    assert overview["modules"] == {"database": "ready"} and overview["access_mode"] == "key"
    assert set(overview) == {"ready", "modules", "storage_mode", "access_mode", "coordination", "platforms"}
    assert overview["platforms"] == {"state": "disabled", "accounts": []}
    catalog = (await client.get("/actions/plugins/catalog")).json()
    entry = catalog["entries"][0]
    assert not catalog["installation_enabled"]
    url = "/actions/plugins/catalog/text_tools/install"
    assert (await client.post(url, json={"sha256": entry["sha256"]})).status_code == 403
    monkeypatch.setattr(get_settings(), "plugin_install_enabled", True)
    try:
        assert (await client.post(url, json={"sha256": entry["sha256"]})).status_code == 201
        assert not plugin_manager.tools_for("operator")
        assert (await client.post(url, json={"sha256": entry["sha256"]})).status_code == 409
    finally:
        await plugin_manager.close()


async def test_resource_id_alone_cannot_delete_another_users_memory_or_read_audio(secure_host):
    _, client, keys = secure_host
    client.headers["Authorization"] = "Bearer " + keys["bob"]
    memory = await client.post(
        "/memory/store", json={"user_id": "bob", "content": "private fact", "embedding": [0.0] * 1024}
    )
    assert memory.status_code == 200
    identifier = memory.json()["entry_id"]
    from voice_layer.media_access import register_voice_asset

    await register_voice_asset("/static/voice/private-test.mp3", "bob")
    client.headers["Authorization"] = "Bearer " + keys["alice"]
    assert (await client.delete("/memory/" + identifier)).status_code == 404
    assert (await client.get("/static/voice/private-test.mp3")).status_code == 404
    assert (await client.post("/memory/recall", json={"query": "fact", "user_id": "bob"})).status_code == 403


async def test_session_claim_race_allows_only_one_owner():
    await init_database_schema()
    history = PersistentSessionMemory()
    session_id = "claim-" + uuid4().hex
    results = await asyncio.gather(
        *(history.authorize_session(session_id, user, claim=True) for user in ("alice", "bob")), return_exceptions=True
    )
    assert results.count(True) == 1
    assert len([result for result in results if isinstance(result, PermissionError)]) == 1
