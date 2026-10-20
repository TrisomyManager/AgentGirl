import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from action_executor.task_agent import TaskAgent, TaskDecision
from core_orchestrator.orchestrator import Orchestrator
from core_orchestrator.specialists import ChatAgent, DeviceAgent, MemoryAgent, SubAgentOrchestrator, delegate_events
from core_orchestrator.state_machine import build_initial_state, node_generate_response, stream_assistant_response
from core_orchestrator.turn_coordinator import TurnCoordinator
from shared_contracts.models import TurnContext, UserProfile
from shared_runtime.database import init_database_schema


def context(message="hello", user="owner", session="session"):
    return TurnContext(
        user=UserProfile(user_id=user),
        session_id=session,
        turn_id=str(uuid.uuid4()),
        user_message=message,
        platform="app",
    )


@pytest.mark.parametrize(
    "message,intent,role,port",
    [
        ("你好", "chat", "chat", None),
        ("我喜欢什么", "memory_query", "memory", "memory"),
        ("我的电脑在线吗", "chat", "device", "device"),
        ("现在几点", "tool_use", "task", "tool"),
        ("不要打开电脑", "device_command", "chat", None),
    ],
)
async def test_specialists_delegate_to_concrete_ports(message, intent, role, port):
    ports = {name: AsyncMock(return_value={"ok": True, "name": name}) for name in ["memory", "device", "tool"]}
    agents = SubAgentOrchestrator(
        chat=ChatAgent(AsyncMock(), None),
        memory=MemoryAgent(ports["memory"]),
        device=DeviceAgent(ports["device"]),
        task_tool=ports["tool"],
        tasks=None,
    )
    selected, result = await agents.delegate(context(message), intent)
    assert selected == role
    for name, callback in ports.items():
        assert callback.await_count == int(name == port)


async def test_multistep_progress_reaches_shared_delegation_stream():
    await init_database_schema()
    choices = iter(
        [TaskDecision(action="tool", tool="get_time"), TaskDecision(action="clarify", message="提醒什么内容？")]
    )

    async def planner(*args):
        return next(choices)

    agents = SubAgentOrchestrator(
        chat=ChatAgent(AsyncMock(), None),
        memory=MemoryAgent(AsyncMock()),
        device=DeviceAgent(AsyncMock()),
        task_tool=AsyncMock(),
        tasks=TaskAgent(planner=planner),
    )
    events = [event async for event in delegate_events(agents, context("先告诉我现在几点，再提醒我"), "tool_use")]
    assert [event["status"] for event in events[:-1]] == ["pending", "success"]
    role, result = events[-1]["_delegation"]
    assert role == "task" and result["data"]["task"]["status"] == "awaiting_input"


async def test_per_session_turn_order_and_other_users_remain_concurrent_and_cleanup():
    coordinator = TurnCoordinator()
    entered, release = asyncio.Event(), asyncio.Event()
    order = []

    async def first():
        async with coordinator.hold("u", "s"):
            order.append(1)
            entered.set()
            await release.wait()

    async def next_turn(user, marker):
        async with coordinator.hold(user, "s"):
            order.append(marker)

    first_worker = asyncio.create_task(first())
    await entered.wait()
    blocked = asyncio.create_task(next_turn("u", 2))
    cancelled = asyncio.create_task(next_turn("u", 9))
    await next_turn("other", 3)
    cancelled.cancel()
    await asyncio.gather(cancelled, return_exceptions=True)
    assert order == [1, 3]
    release.set()
    await asyncio.gather(first_worker, blocked)
    assert order == [1, 3, 2] and coordinator._entries == {}


async def test_normal_and_streaming_calls_share_the_same_session_lock(monkeypatch):
    orchestrator = Orchestrator()
    entered, release = asyncio.Event(), asyncio.Event()
    order = []

    async def normal(tc):
        order.append("normal")
        entered.set()
        await release.wait()
        return {}

    async def stream(tc):
        order.append("stream")
        yield {"event": "done"}

    monkeypatch.setattr(orchestrator, "_process_turn", normal)
    monkeypatch.setattr(orchestrator, "_process_turn_stream", stream)
    tc = context()
    worker = asyncio.create_task(orchestrator.process_turn(tc))
    await entered.wait()

    async def consume():
        return [event async for event in orchestrator.process_turn_stream(tc)]

    streaming = asyncio.create_task(consume())
    await asyncio.sleep(0)
    assert order == ["normal"]
    release.set()
    await asyncio.gather(worker, streaming)
    assert order == ["normal", "stream"]
    assert orchestrator._turn_coordinator._entries == {}


@pytest.mark.parametrize("streaming", [False, True])
async def test_memory_query_has_identical_deterministic_reply_in_both_paths(monkeypatch, streaming):
    import core_orchestrator.state_machine as sm
    from action_executor.registry import ActionResult, get_registry

    tc = context("我喜欢什么")

    async def classify(state):
        state["intent"] = "memory_query"
        return state

    async def passthrough(state):
        return state

    monkeypatch.setattr(sm, "node_classify_intent", classify)
    for name in [
        "node_recall_memory",
        "prepare_reaction_state",
        "prepare_reply_decision",
        "node_synthesize_voice",
        "node_generate_action",
        "node_send_response",
        "node_sync_memory",
    ]:
        monkeypatch.setattr(sm, name, passthrough)
    monkeypatch.setattr(
        get_registry().definition("query_memory"),
        "handler",
        AsyncMock(return_value=ActionResult(message="你喜欢喝茶。")),
    )
    monkeypatch.setattr(sm, "_record_tool_interaction_to_memory", AsyncMock())
    monkeypatch.setattr(
        sm, "_generate_response_monolithic", AsyncMock(side_effect=AssertionError("Must use memory result"))
    )
    if streaming:
        events = [event async for event in stream_assistant_response(tc)]
        state = events[-1]["_state"]
        assert "".join(event["text"] for event in events if event["event"] == "token") == "你喜欢喝茶。"
    else:
        state = build_initial_state(tc)
        state["intent"] = "memory_query"
        state = await node_generate_response(state)
    assert state["assistant_message"] == "你喜欢喝茶。" and state["specialist"] == "memory"
