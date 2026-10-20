import uuid

import httpx
import pytest
from fastapi import FastAPI

from action_executor.api import router
from action_executor.task_agent import TaskDecision, task_agent
from action_executor.task_store import task_store
from shared_runtime.database import init_database_schema


@pytest.fixture
async def client():
    await init_database_schema()
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as value:
        yield value


async def test_task_endpoints_persist_receipts_resume_and_hide_other_users(client, monkeypatch):
    choices = iter(
        [
            TaskDecision(action="tool", tool="get_time"),
            TaskDecision(action="clarify", message="提醒什么？"),
            TaskDecision(action="finish"),
        ]
    )

    async def plan(*args):
        return next(choices)

    monkeypatch.setattr(task_agent, "planner", plan)
    owner = "task-api-" + str(uuid.uuid4())
    response = await client.post(
        "/actions/tasks", json={"user_id": owner, "session_id": "s", "request": "先查时间，再提醒我"}
    )
    assert response.status_code == 200
    run = response.json()["task"]
    task_id = run["id"]
    assert run["status"] == "awaiting_input" and len(run["steps"]) == 1
    assert (await client.get(f"/actions/tasks/{task_id}", params={"user_id": "other"})).status_code == 404
    assert (await client.delete(f"/actions/tasks/{task_id}", params={"user_id": "other"})).status_code == 404
    assert (
        await client.post(f"/actions/tasks/{task_id}/resume", json={"user_id": "other", "clarification": "x"})
    ).status_code == 404
    assert (await client.get("/actions/tasks", params={"user_id": "other"})).json()["tasks"] == []
    response = await client.post(
        f"/actions/tasks/{task_id}/resume", json={"user_id": owner, "clarification": "只需要时间就好"}
    )
    assert response.json()["ok"] and len(response.json()["task"]["steps"]) == 1
    state = (await client.get("/actions/user_state", params={"user_id": owner})).json()
    assert state["tasks"]["completed_recent"][0]["id"] == task_id
    assert (
        await client.post(f"/actions/tasks/{task_id}/resume", json={"user_id": owner, "clarification": "x"})
    ).status_code == 409


async def test_task_cancel_endpoint_stops_awaiting_work(client):
    run, _ = await task_store.create(user_id="cancel-api", session_id="s", turn_id=str(uuid.uuid4()), request="test")
    await task_store.finish(run["id"], "cancel-api", "awaiting_input", "补充？")
    result = await client.delete(f"/actions/tasks/{run['id']}", params={"user_id": "cancel-api"})
    assert result.status_code == 200 and result.json()["cancelled"]
    assert (await client.get(f"/actions/tasks/{run['id']}", params={"user_id": "cancel-api"})).json()[
        "status"
    ] == "cancelled"
