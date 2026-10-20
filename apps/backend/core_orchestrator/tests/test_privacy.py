import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from core_orchestrator import privacy
from core_orchestrator.tests.test_access_policy import secure_host as secure_host_fixture
from memory_system.session_store import PersistentSessionMemory, SessionDigestORM
from shared_runtime.database import AsyncSessionLocal, Base
from shared_runtime.user_lifecycle import StaleUserOperation, user_operation
from voice_layer.media_access import register_voice_asset

secure_host = secure_host_fixture


async def seed_user(client, keys, user):
    client.headers["Authorization"] = "Bearer " + keys[user]
    result = await client.post(
        "/memory/store", json={"user_id": user, "content": user + " private fact", "embedding": [0.0] * 1024}
    )
    assert result.status_code == 200
    session_id = user + "-" + uuid4().hex
    history = PersistentSessionMemory()
    await history.authorize_session(session_id, user, claim=True)
    await history.add_turn(session_id, uuid4().hex, user + " private turn", "reply", metadata={"user_id": user})
    await history.save_digest(session_id, {"text": user + " private summary"})
    return session_id


async def test_export_and_erasure_cover_owned_data_without_touching_other_users(secure_host, tmp_path, monkeypatch):
    _, client, keys = secure_host
    monkeypatch.setenv("COMPANION_VOICE_TEMP_DIR", str(tmp_path))
    alice_session = await seed_user(client, keys, "alice")
    from core_orchestrator.state_machine import get_debug_system_prompt_snapshot, record_debug_system_prompt
    record_debug_system_prompt(alice_session, "alice", "private prompt")
    bob_session = await seed_user(client, keys, "bob")
    for user in ("alice", "bob"):
        (tmp_path / (user + ".mp3")).write_bytes(b"synthetic-audio")
        await register_voice_asset("/static/voice/" + user + ".mp3", user)
    client.headers["Authorization"] = "Bearer " + keys["alice"]
    graph = await client.get("/memory/user/alice/graph")
    assert graph.status_code == 200 and "alice private fact" in graph.text
    assert "bob private" not in graph.text
    assert (await client.get("/memory/user/bob/graph")).status_code == 403
    response = await client.get("/privacy/user/alice/export")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["format"] == "companion.user-data.v1"
    encoded = json.dumps(data)
    assert "alice private fact" in encoded and "alice private turn" in encoded and "alice private summary" in encoded
    assert "bob private" not in encoded
    assert keys["alice"] not in encoded and "embedding" not in data["data"]["memories"][0]
    assert {table.name for table in privacy.user_tables()} <= set(data["data"])
    assert (await client.get("/privacy/user/bob/export")).status_code == 403
    assert (await client.post("/privacy/user/alice/erase", json={"confirmation": "yes"})).status_code == 400
    response = await client.post("/privacy/user/alice/erase", json={"confirmation": "删除我的全部数据"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert get_debug_system_prompt_snapshot()["system_prompt"] is None
    async with AsyncSessionLocal() as session:
        for table in privacy.user_tables():
            assert (await session.execute(select(table).where(table.c.user_id == "alice"))).first() is None, table.name
        assert await session.get(SessionDigestORM, alice_session) is None
        assert await session.get(SessionDigestORM, bob_session) is not None
        job = await session.get(privacy.ErasureJobORM, "alice")
        assert job.pending_json == "{}"
    assert not (tmp_path / "alice.mp3").exists()
    assert (tmp_path / "bob.mp3").exists()
    assert (
        await client.post("/privacy/user/alice/erase", json={"confirmation": "删除我的全部数据"})
    ).status_code == 200


async def test_failed_external_cleanup_is_durable_blocks_new_data_and_can_retry(secure_host, monkeypatch):
    _, client, keys = secure_host
    await seed_user(client, keys, "alice")
    original = privacy._cleanup_resource

    async def unavailable(name, payload, user):
        if name == "voice_files":
            raise OSError("synthetic unavailable storage")
        await original(name, payload, user)

    monkeypatch.setattr(privacy, "_cleanup_resource", unavailable)
    response = await client.post("/privacy/user/alice/erase", json={"confirmation": "删除我的全部数据"})
    assert response.status_code == 202
    assert response.json()["pending"] == ["voice_files"]
    assert not await privacy.no_pending_erasure("alice")
    assert (await client.get("/memory/user/alice/list")).status_code == 409
    assert (await client.get("/privacy/user/alice/status")).json()["status"] == "pending"
    client.headers["Authorization"] = "Bearer " + keys["bob"]
    assert (await client.get("/memory/user/bob/list")).status_code == 200
    client.headers["Authorization"] = "Bearer " + keys["alice"]
    monkeypatch.setattr(privacy, "_cleanup_resource", original)
    assert (await client.post("/privacy/user/alice/erase", json={"confirmation": "删除我的全部数据"})).json()[
        "status"
    ] == "completed"
    assert (await client.get("/memory/user/alice/list")).status_code == 200


async def test_erasure_joins_active_work_and_sql_rejects_a_detached_old_writer(secure_host):
    _, client, keys = secure_host
    await seed_user(client, keys, "alice")
    started, release = asyncio.Event(), asyncio.Event()
    children = []

    async def late_writer():
        await release.wait()
        async with AsyncSessionLocal() as session:
            table = Base.metadata.tables["care_users"]
            await session.execute(table.insert().values(user_id="alice", preferences_json="{}"))
            await session.commit()

    async def ongoing_call():
        async with user_operation("alice"):
            children.append(asyncio.create_task(late_writer()))
            started.set()
            await asyncio.Future()

    task = asyncio.create_task(ongoing_call())
    await started.wait()
    response = await client.post("/privacy/user/alice/erase", json={"confirmation": "删除我的全部数据"})
    assert response.status_code == 200
    assert task.done() and task.cancelled()
    release.set()
    with pytest.raises(StaleUserOperation):
        await children[0]
    async with AsyncSessionLocal() as session:
        table = Base.metadata.tables["care_users"]
        assert (await session.execute(select(table).where(table.c.user_id == "alice"))).first() is None


async def test_erasure_also_cancels_requests_that_are_still_authorizing_the_session(secure_host):
    from shared_runtime.access import AccessMiddleware

    app, client, keys = secure_host
    await seed_user(client, keys, "alice")
    boundary = app.middleware_stack
    while not isinstance(boundary, AccessMiddleware):
        boundary = boundary.app
    original = boundary.authorize
    started = asyncio.Event()

    async def slow_authorize(scope, body, principal):
        if scope["path"] == "/orchestrator/turn":
            started.set()
            await asyncio.Future()
        return await original(scope, body, principal)

    boundary.authorize = slow_authorize
    pending = asyncio.create_task(
        client.post(
            "/orchestrator/turn",
            json={
                "user": {"user_id": "alice"},
                "session_id": "claim-after-erasure",
                "user_message": "old request",
            },
        )
    )
    await asyncio.wait_for(started.wait(), 2)
    response = await client.post("/privacy/user/alice/erase", json={"confirmation": "删除我的全部数据"})
    assert response.status_code == 200
    assert (await pending).status_code == 409


async def test_cancelled_voice_ownership_registration_removes_the_new_file(secure_host, tmp_path, monkeypatch):
    from shared_runtime.access import Principal, current_principal
    from voice_layer import media_access
    from voice_layer.audio_utils import save_temp_audio

    folder = tmp_path / "voice"
    monkeypatch.setenv("COMPANION_VOICE_TEMP_DIR", str(folder))

    async def cancelled(*_args):
        raise asyncio.CancelledError()

    monkeypatch.setattr(media_access, "register_voice_asset", cancelled)
    token = current_principal.set(Principal("alice", "user"))
    try:
        with pytest.raises(asyncio.CancelledError):
            await save_temp_audio(b"synthetic-audio")
    finally:
        current_principal.reset(token)
    assert not list(folder.iterdir())
