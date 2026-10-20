import base64
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image

from core_orchestrator import state_machine as sm
from core_orchestrator.orchestrator import Orchestrator
from shared_contracts.models import PersonaProfile, TurnContext, UserProfile
from shared_runtime.config import get_settings
from shared_runtime.image_input import IMAGE_PROMPT


def context(**kwargs):
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), "red").save(buffer, "PNG")
    return TurnContext(
        turn_id=uuid4().hex,
        session_id=uuid4().hex,
        user=UserProfile(user_id=uuid4().hex),
        platform="app",
        user_message="打开电脑浏览器，再提醒我喝水，先看看图片",
        image_urls=["data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()],
        **kwargs,
    )


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setattr(sm, "_is_monolithic", lambda: True)
    monkeypatch.setattr(get_settings(), "enable_memory_pipeline", False)
    tool = AsyncMock()
    monkeypatch.setattr(sm, "_try_action_executor", tool)
    monkeypatch.setattr(sm, "_try_device_actions_by_keyword", tool)

    async def recall(state):
        state["persona_profile"] = PersonaProfile(name="Companion")
        return state

    async def identity(state):
        return state

    monkeypatch.setattr(sm, "node_recall_memory", recall)
    for name in [
        "prepare_reaction_state",
        "prepare_reply_decision",
        "node_synthesize_voice",
        "node_generate_action",
        "node_send_response",
        "node_sync_memory",
    ]:
        monkeypatch.setattr(sm, name, identity)
    generated = AsyncMock(return_value={"assistant_message": "红色方块"})

    async def stream(**kwargs):
        await generated(**kwargs)
        yield "红色"
        yield "方块"

    fake = SimpleNamespace(
        has_configured_provider=lambda: True, generate=generated, generate_stream=stream, close=AsyncMock()
    )
    monkeypatch.setattr("shared_runtime.llm_client.LLMClient", lambda: fake)
    orch = Orchestrator()
    monkeypatch.setattr(orch, "_record_user_activity", AsyncMock())
    orch._graph = sm.build_graph()
    return orch, generated, tool, fake


@pytest.mark.parametrize("streaming", [False, True])
async def test_real_entrypoints_forward_pixels_and_bypass_all_tools(host, streaming):
    orch, generated, tool, fake = host
    tc = context()
    if streaming:
        events = [event async for event in orch.process_turn_stream(tc)]
        result = events[-1]
    else:
        result = await orch.process_turn(tc)
    assert result["assistant_message"] == "红色方块" and result["intent"] == "chat"
    assert tc.has_image and tc.image_urls[0].startswith("data:image/jpeg;base64,")
    assert generated.call_args.kwargs["image_urls"] == tc.image_urls
    assert IMAGE_PROMPT in generated.call_args.kwargs["system_prompt"]
    assert tc.image_urls[0] not in generated.call_args.kwargs["system_prompt"]
    tool.assert_not_awaited()
    fake.close.assert_awaited_once()


@pytest.mark.parametrize("streaming", [False, True])
async def test_bad_images_stop_before_provider_or_tools(host, streaming):
    orch, generated, tool, _ = host
    tc = context()
    tc.image_urls = ["https://127.0.0.1/private"]
    result = ([event async for event in orch.process_turn_stream(tc)])[-1] if streaming else await orch.process_turn(tc)
    assert result["error"] and not result["assistant_message"]
    generated.assert_not_awaited()
    tool.assert_not_awaited()


async def test_missing_provider_is_explicit_for_image_only_input(host):
    orch, generated, _, fake = host
    fake.has_configured_provider = lambda: False
    tc = context()
    tc.user_message = ""
    result = await orch.process_turn(tc)
    assert tc.user_message and "支持图片的模型" in result["assistant_message"]
    generated.assert_not_awaited()


async def test_image_history_keeps_text_but_no_pixels_or_derived_personal_facts(monkeypatch):
    from memory_system.session_store import PersistentSessionMemory
    from memory_system.working import WorkingMemory
    from shared_runtime.database import init_database_schema

    await init_database_schema()
    wm = WorkingMemory()
    monkeypatch.setattr("memory_system.working.get_working_memory", lambda: wm)
    monkeypatch.setattr(sm, "_is_monolithic", lambda: False)
    monkeypatch.setattr(get_settings(), "enable_memory_pipeline", True)
    derived = AsyncMock()
    monkeypatch.setattr(sm.memory_client, "post", derived)
    tc = context()
    tc.has_image = True
    state = sm.build_minimal_memory_sync_state(tc, "一张红色图片")
    await sm.sync_completed_turn_to_memory(turn_context=tc, orchestration_state=state)
    derived.assert_not_awaited()
    history = await PersistentSessionMemory().get_session_turns(tc.session_id)
    assert history[0]["metadata"]["has_image"] is True
    assert history[0]["user_message"] == tc.user_message
    assert "base64" not in str(history)
