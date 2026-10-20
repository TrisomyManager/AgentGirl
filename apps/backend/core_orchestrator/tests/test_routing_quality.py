"""Curated intent regression set plus model failures and execution-boundary checks."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core_orchestrator.intent_router import Intent, IntentRouter
from core_orchestrator.state_machine import _try_action_executor, _try_device_actions_by_keyword
from shared_contracts.models import TurnContext, UserProfile

CASES = json.loads((Path(__file__).parent / "data" / "intent_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
async def test_current_request_routing_regression(case):
    router = IntentRouter()
    result = router._heuristic_classify(case["message"], case.get("context"))
    assert result.intent.value == case["expected"]


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        "[]",
        '{"intent":"missing","confidence":0.9}',
        '{"intent":"device_command","confidence":NaN}',
        '{"intent":"device_command","confidence":2}',
        '{"intent":"device_command","confidence":0.9,"entities":null}',
    ],
)
async def test_malformed_model_output_falls_back_to_current_request(raw):
    llm = type("Model", (), {"ainvoke": AsyncMock(return_value=type("Response", (), {"content": raw})())})()
    result = await IntentRouter(llm=llm).classify("我想聊聊公园里的风景", "电脑在线吗")
    assert result.intent == Intent.CHAT
    assert result.source == "rules"


async def test_low_confidence_and_conflicting_model_cannot_repeat_tools_or_change_a_reminder_to_recall():
    llm = type(
        "Model",
        (),
        {
            "ainvoke": AsyncMock(
                return_value=type(
                    "Response", (), {"content": '{"intent":"memory_query","confidence":0.99,"entities":{}}'}
                )()
            )
        },
    )()
    result = await IntentRouter(llm=llm).classify("记得提醒我喝水")
    assert result.intent == Intent.TOOL_USE
    assert result.source == "rules"
    llm.ainvoke.reset_mock()
    assert (await IntentRouter(llm=llm).classify("好的", "打开网址")).intent == Intent.CHAT
    llm.ainvoke.assert_not_awaited()
    llm.ainvoke.return_value.content = '{"intent":"tool_use","confidence":0.1,"entities":{}}'
    assert (await IntentRouter(llm=llm).classify("今天心情不错")).intent == Intent.CHAT


async def test_model_timeout_is_bounded_and_task_cancellation_propagates(monkeypatch):
    from shared_runtime.config import get_settings

    monkeypatch.setattr(get_settings(), "intent_router_timeout_seconds", 0.01)

    async def wait(_messages):
        await asyncio.sleep(5)

    llm = type("Model", (), {"ainvoke": AsyncMock(side_effect=wait)})()
    assert (await IntentRouter(llm=llm).classify("今天心情很好")).intent == Intent.CHAT
    llm.ainvoke.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await IntentRouter(llm=llm).classify("今天心情很好")


@pytest.mark.parametrize("message", ["我叫什么", "我喜欢什么", "我说过什么"])
async def test_direct_personal_recall_has_priority_over_an_incorrect_chat_label(message):
    llm = type(
        "Model",
        (),
        {
            "ainvoke": AsyncMock(
                return_value=type("Response", (), {"content": '{"intent":"chat","confidence":0.99,"entities":{}}'})()
            )
        },
    )()
    result = await IntentRouter(llm=llm).classify(message)
    assert result.intent == Intent.MEMORY_QUERY
    assert result.source == "rules"


@pytest.mark.parametrize(
    "message", ["你在线吗", "不要给电脑发通知", "先别打开网址 https://example.com", "如何打开网址"]
)
async def test_non_requests_never_reach_device_dispatch_even_with_an_incorrect_model_intent(message, monkeypatch):
    dispatch = AsyncMock()
    registry = type(
        "Registry", (), {"find_by_keyword": lambda _self, _message: "device_notify", "dispatch": dispatch}
    )()
    monkeypatch.setattr("action_executor.registry.get_registry", lambda: registry)
    context = TurnContext(
        turn_id="t", session_id="s", user=UserProfile(user_id="u"), user_message=message, platform="app"
    )
    assert await _try_action_executor(context, "device_command") is None
    assert await _try_device_actions_by_keyword(context) is None
    dispatch.assert_not_awaited()


async def test_cancellation_does_not_dispatch_the_creation_handler_even_when_its_keyword_matches_first(monkeypatch):
    from action_executor.registry import ActionResult

    dispatch = AsyncMock(return_value=ActionResult(ok=True, message="已取消"))
    registry = type("Registry", (), {"find_by_keyword": lambda _self, _message: "set_reminder", "dispatch": dispatch})()
    monkeypatch.setattr("action_executor.registry.get_registry", lambda: registry)
    context = TurnContext(
        turn_id="t", session_id="s", user=UserProfile(user_id="u"), user_message="不用再提醒我喝水了", platform="app"
    )
    result = await _try_action_executor(context, "tool_use")
    assert result["name"] == "cancel_reminder"
    dispatch.assert_awaited_once_with(
        "cancel_reminder",
        {
            "user_id": "u",
            "session_id": "s",
            "raw_text": "不用再提醒我喝水了",
        },
    )
