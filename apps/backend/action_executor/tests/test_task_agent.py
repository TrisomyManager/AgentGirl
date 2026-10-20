import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from action_executor.registry import ActionRegistry, ActionResult
from action_executor.task_agent import TaskAgent, TaskDecision
from action_executor.task_store import TaskStore
from action_executor.tool_catalog import ToolCatalog, ToolContext
from shared_runtime.database import init_database_schema


@pytest.fixture(autouse=True)
async def schema():
    await init_database_schema()


def context(user="task-owner", message="test task"):
    return ToolContext(user, "session", str(uuid.uuid4()), message)


def planner_sequence(*decisions):
    iterator = iter(decisions)

    async def planner(request, tools, steps):
        return next(iterator)

    return planner


def catalog_with_counter():
    registry, seen = ActionRegistry(), []

    @registry.register(
        "write",
        "Test effect",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        requires_user_id=True,
    )
    async def handler(params):
        seen.append(params)
        return ActionResult(ok=True, message="实际执行完成", data={"count": len(seen)})

    return ToolCatalog(registry), seen


async def test_multi_step_real_reminder_and_grounded_summary_and_turn_replay():
    decision = planner_sequence(
        TaskDecision(action="tool", tool="get_time"),
        TaskDecision(action="tool", tool="set_reminder", arguments={"text": "休息", "delay_seconds": 600}),
        TaskDecision(action="finish", message="捏造的未执行操作也成功"),
    )
    agent = TaskAgent(planner=decision)
    ctx = context()
    progress = []

    async def observe(event):
        progress.append(event)

    result = await agent.execute(ctx, progress=observe)
    run = result.data["task"]
    assert result.ok and run["status"] == "completed"
    assert [step["tool_name"] for step in run["steps"]] == ["get_time", "set_reminder"]
    assert "捏造" not in result.message and "休息" in result.message
    assert [event["status"] for event in progress] == ["pending", "success", "pending", "success"]
    assert (await agent.execute(ctx)).data["task"]["id"] == run["id"]
    from action_executor.reminders import get_reminders_store

    pending = await get_reminders_store().list_for_user(ctx.user_id)
    assert len([reminder for reminder in pending if reminder.text == "休息"]) == 1
    assert await TaskStore().get(run["id"], "other-user") is None
    assert (await TaskStore().get(run["id"], ctx.user_id))["steps"] == run["steps"]


@pytest.mark.parametrize(
    "decision",
    [
        TaskDecision(action="tool", tool="unknown"),
        TaskDecision(action="tool", tool="write", arguments={"text": "x", "user_id": "other"}),
        {"action": "execute arbitrary code"},
    ],
)
async def test_invalid_or_spoofed_plans_do_not_execute(decision):
    catalog, seen = catalog_with_counter()
    agent = TaskAgent(catalog=catalog, planner=planner_sequence(decision))
    result = await agent.execute(context())
    assert not result.ok and not seen


@pytest.mark.parametrize("broken", [False, True])
async def test_request_review_rejection_or_failure_prevents_planning_and_tools(broken):
    catalog, seen = catalog_with_counter()
    planner = AsyncMock()
    agent = TaskAgent(catalog=catalog, planner=planner)

    def review(text):
        if broken:
            raise RuntimeError("synthetic unavailable review")
        return "review refused"

    agent.request_filter = review
    assert not (await agent.execute(context())).ok
    planner.assert_not_awaited()
    assert not seen


async def test_resume_reviews_the_combined_request_before_any_new_step():
    catalog, seen = catalog_with_counter()
    planner = AsyncMock(return_value=TaskDecision(action="clarify", message="补充？"))
    agent = TaskAgent(catalog=catalog, planner=planner)
    agent.request_filter = lambda text: "combined rejected" if "BEGIN" in text and "END" in text else None
    result = await agent.execute(context(message="BEGIN"))
    run_id = result.data["task"]["id"]
    result = await agent.execute(context(message="END"), resume_run_id=run_id)
    assert result.data["task"]["status"] == "failed" and result.message == "combined rejected"
    assert planner.await_count == 1 and not seen


async def test_reviewed_plans_and_observations_cannot_bypass_the_public_output_policy():
    catalog, seen = catalog_with_counter()
    agent = TaskAgent(
        catalog=catalog,
        planner=planner_sequence(TaskDecision(action="tool", tool="write", arguments={"text": "SYNTHETIC_BLOCK"})),
    )
    agent.response_filter = lambda text: "filtered" if "SYNTHETIC_BLOCK" in text else None
    result = await agent.execute(context())
    assert not seen and result.message == "filtered" and not result.data["task"]["steps"]

    agent.planner = planner_sequence(TaskDecision(action="tool", tool="write", arguments={"text": "safe"}))
    agent.response_filter = lambda text: "filtered observation" if "实际执行完成" in text else None
    result = await agent.execute(context())
    assert len(seen) == 1 and result.message == "filtered observation"
    assert "实际执行完成" not in str(result.data)


async def test_duplicate_mutations_and_disallowed_tools_are_stopped():
    catalog, seen = catalog_with_counter()
    step = TaskDecision(action="tool", tool="write", arguments={"text": "x"})
    agent = TaskAgent(catalog=catalog, planner=planner_sequence(step, step))
    result = await agent.execute(context())
    assert not result.ok and len(seen) == 1 and "重复" in result.message
    second = TaskAgent(catalog=catalog, planner=planner_sequence(step))
    assert not (await second.execute(context(), allowed_tools=set())).ok
    assert len(seen) == 1


async def test_clarification_resumes_without_replaying_completed_steps():
    catalog, seen = catalog_with_counter()
    agent = TaskAgent(
        catalog=catalog,
        planner=planner_sequence(
            TaskDecision(action="tool", tool="write", arguments={"text": "first"}),
            TaskDecision(action="clarify", message="下一条写什么？"),
            TaskDecision(action="tool", tool="write", arguments={"text": "second"}),
            TaskDecision(action="finish"),
        ),
    )
    ctx = context()
    result = await agent.execute(ctx)
    task_id = result.data["task"]["id"]
    assert result.data["task"]["status"] == "awaiting_input"
    assert not (await agent.execute(context("other"), resume_run_id=task_id)).ok
    result = await agent.execute(context(message="second"), resume_run_id=task_id)
    assert result.ok and len(seen) == 2
    assert [step["position"] for step in result.data["task"]["steps"]] == [0, 1]


async def test_timeout_persists_unknown_outcome_and_does_not_replay():
    registry = ActionRegistry()
    entered = asyncio.Event()

    @registry.register("slow", "Slow test", read_only=False)
    async def slow(params):
        entered.set()
        await asyncio.Event().wait()

    agent = TaskAgent(
        catalog=ToolCatalog(registry),
        tool_timeout=0.03,
        planner=planner_sequence(TaskDecision(action="tool", tool="slow")),
    )
    ctx = context()
    result = await agent.execute(ctx)
    assert entered.is_set() and result.data["task"]["status"] == "interrupted"
    assert result.data["task"]["steps"][0]["status"] == "outcome_unknown"
    assert (await agent.execute(ctx)).data["task"] == result.data["task"]


async def test_owner_cancellation_during_planning_prevents_execution():
    catalog, seen = catalog_with_counter()
    entered = asyncio.Event()

    async def planner(*args):
        entered.set()
        await asyncio.Event().wait()

    agent = TaskAgent(catalog=catalog, planner=planner)
    ctx = context()
    worker = asyncio.create_task(agent.execute(ctx))
    await entered.wait()
    run_id = next(iter(agent._active))
    assert not await agent.cancel(run_id, "other")
    assert await agent.cancel(run_id, ctx.user_id)
    result = await worker
    assert result.data["task"]["status"] == "cancelled"
    assert not seen
    assert (await TaskStore().get(run_id, ctx.user_id))["status"] == "cancelled"


async def test_restart_recovery_marks_inflight_steps_unknown():
    store, ctx = TaskStore(), context()
    run, _ = await store.create(user_id=ctx.user_id, session_id=ctx.session_id, turn_id=ctx.turn_id, request="test")
    await store.start_step(run["id"], 0, "write", {})
    await store.recover_interrupted()
    recovered = await store.get(run["id"], ctx.user_id)
    assert recovered["status"] == "interrupted" and recovered["steps"][0]["status"] == "outcome_unknown"


async def test_planner_deadline_and_step_count_are_bounded():
    catalog, seen = catalog_with_counter()

    async def slow(*args):
        await asyncio.Event().wait()

    agent = TaskAgent(catalog=catalog, planner=slow, planner_timeout=0.02)
    assert (await agent.execute(context())).data["task"]["status"] == "interrupted"
    agent = TaskAgent(
        catalog=catalog,
        max_steps=1,
        planner=planner_sequence(
            TaskDecision(action="tool", tool="write", arguments={"text": "one"}),
            TaskDecision(action="tool", tool="write", arguments={"text": "two"}),
        ),
    )
    assert (await agent.execute(context())).data["task"]["status"] == "limit_reached"
    assert len(seen) == 1


def test_effect_scope_respects_negation_cancellation_and_external_opt_in():
    from action_executor.task_policy import task_tool_scope

    tools = [
        {"name": "get_time", "annotations": {"readOnlyHint": True}},
        {"name": "external__change", "annotations": {"readOnlyHint": False}},
    ]
    assert task_tool_scope("先查时间，再提醒我喝水", tools) == {"get_time", "set_reminder"}
    assert task_tool_scope("不要给电脑发通知", tools) == {"get_time"}
    assert task_tool_scope("不用再提醒我喝水了", tools) == {"get_time", "cancel_reminder"}
    assert "external__change" not in task_tool_scope("先看时间然后聊天", tools)
    assert "external__change" in task_tool_scope("使用 external 服务执行我的任务", tools)
