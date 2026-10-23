import time
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from action_executor.desktop_context import DesktopObservation, ProactivePolicy
from action_executor.proactive_care import ProactiveCareScheduler
from shared_runtime.database import init_database_schema
from shared_runtime.features import FeatureManager


async def test_feature_and_policy_http_contracts_persist_and_validate(tmp_path, monkeypatch):
    import main

    manager = FeatureManager(tmp_path / "features.json", defaults={"desktop_context", "proactive_care"})
    monkeypatch.setattr(main, "features", manager)
    monkeypatch.setattr("action_executor.api.get_feature_manager", lambda: manager)
    app = main.create_app()
    await init_database_schema()
    uid = "policy-" + uuid.uuid4().hex
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        before = (await client.get("/settings/features")).json()
        bad = await client.put("/settings/features", json={"enabled": ["desktop_context"]})
        assert bad.status_code == 422
        assert (await client.get("/settings/features")).json() == before
        saved = await client.put("/settings/features", json={"enabled": []})
        assert saved.status_code == 200
        assert saved.json()["restart_required"]
        assert "desktop_context" in saved.json()["active_enabled"]
        context = {"user_id": uid, "device_id": "pc", "foreground_app": "code.exe"}
        assert (await client.post("/actions/proactive/context", json=context)).status_code == 409
        policy = ProactivePolicy(desktop_enabled=True, allowed_apps=["CODE.EXE"]).model_dump()
        assert (await client.put(f"/actions/proactive/preferences?user_id={uid}", json=policy)).status_code == 200
        read = (await client.get(f"/actions/proactive/preferences?user_id={uid}")).json()
        assert read["policy"]["allowed_apps"] == ["code.exe"]
        observation = await client.post("/actions/proactive/context", json=context)
        assert observation.status_code == 200
        assert observation.json()["reason"] == "dwelling"
        pixels = await client.post("/actions/proactive/context", json={**context, "screenshot": "no"})
        assert pixels.status_code == 422


async def test_context_is_rechecked_after_generation_and_memory_commits_only_after_push(monkeypatch):
    scheduler = ProactiveCareScheduler()
    policy = ProactivePolicy(desktop_enabled=True, allowed_apps=["code.exe"], dwell_seconds=15)
    monkeypatch.setattr("action_executor.proactive_care.read_policy", AsyncMock(return_value=policy))
    monkeypatch.setattr("action_executor.proactive_care.get_feature_manager",
                        lambda: SimpleNamespace(is_active=lambda _: True))
    scheduler._store = AsyncMock()
    scheduler._store.last_sent_for_user.return_value = None
    scheduler._store.count_today.return_value = 0
    scheduler._store.add.return_value = SimpleNamespace(id="delivered")
    scheduler._bus = AsyncMock()
    commit = AsyncMock()
    observation = DesktopObservation(user_id="alice", device_id="pc", foreground_app="code.exe")
    scheduler.context_gate.update(observation, now=time.monotonic() - 20)

    async def generate_then_fullscreen(**_kwargs):
        scheduler.context_gate.update(observation.model_copy(update={"fullscreen": True}))
        return {"assistant_message": "休息一下吧", "_commit_memory": commit}

    monkeypatch.setattr(scheduler, "_call_orchestrator", generate_then_fullscreen)
    assert await scheduler._evaluate_user("alice", datetime.now(UTC), False) == 0
    commit.assert_not_awaited()
    scheduler._store.add.assert_not_awaited()
    scheduler._bus.publish.assert_not_awaited()
    scheduler.context_gate.update(observation)
    order = []

    async def publish(_event):
        order.append("push")

    async def commit_after_push():
        order.append("memory")

    scheduler._bus.publish.side_effect = publish
    monkeypatch.setattr(scheduler, "_call_orchestrator", AsyncMock(return_value={
        "assistant_message": "休息一下吧", "_commit_memory": commit_after_push,
    }))
    assert await scheduler._evaluate_user("alice", datetime.now(UTC), False) == 1
    assert order == ["push", "memory"]
    assert await scheduler._evaluate_user("alice", datetime.now(UTC), False) == 0
