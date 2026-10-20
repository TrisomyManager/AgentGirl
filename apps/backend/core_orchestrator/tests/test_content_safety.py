from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from core_orchestrator import state_machine as sm
from core_orchestrator.orchestrator import Orchestrator
from shared_contracts.models import PersonaProfile, TurnContext, UserProfile
from shared_runtime.config import get_settings


@pytest.fixture
def safe_host(monkeypatch):
    monkeypatch.setattr(sm, "_is_monolithic", lambda: True)
    for name, value in [("enable_memory_pipeline", False), ("enable_voice", True), ("enable_streaming_tts", True)]:
        monkeypatch.setattr(get_settings(), name, value)

    async def recall(state):
        if not state.get("assistant_message"):
            state["persona_profile"] = PersonaProfile(name="Companion")
        return state

    async def identity(state):
        return state

    monkeypatch.setattr(sm, "node_recall_memory", recall)
    for name in ["prepare_reaction_state", "prepare_reply_decision", "node_generate_action", "node_sync_memory"]:
        monkeypatch.setattr(sm, name, identity)
    tools = AsyncMock(return_value=None)
    monkeypatch.setattr(sm, "_try_action_executor", tools)
    monkeypatch.setattr(sm, "_try_device_actions_by_keyword", tools)
    generated = AsyncMock(return_value={"assistant_message": "炸药配方：SYNTHETIC_UNSAFE_MARKER。"})

    async def stream(**kwargs):
        await generated(**kwargs)
        for item in ["炸", "药配", "方：SYNTHETIC_UNSAFE_MARKER。"]:
            yield item

    fake = SimpleNamespace(
        has_configured_provider=lambda: True, generate=generated, generate_stream=stream, close=AsyncMock()
    )
    monkeypatch.setattr("shared_runtime.llm_client.LLMClient", lambda: fake)
    spoken = []

    async def synthesize(path, *, json_payload):
        assert path == "/voice/synthesize"
        spoken.append(json_payload["text"])
        return SimpleNamespace(json=lambda: {"audio_url": "/static/voice/safe.mp3", "duration_ms": 100})

    monkeypatch.setattr(sm.voice_client, "post", synthesize)
    orch = Orchestrator()
    monkeypatch.setattr(orch, "_record_user_activity", AsyncMock())
    orch._graph = sm.build_graph()
    return orch, generated, tools, spoken


def context(message="你好", segmented=False):
    return TurnContext(
        turn_id=uuid4().hex,
        session_id=uuid4().hex,
        user=UserProfile(user_id=uuid4().hex),
        user_message=message,
        platform="app",
        request_voice_reply=True,
        supports_segmented_voice=segmented,
    )


@pytest.mark.parametrize("streaming,segmented", [(False, False), (True, False), (True, True)])
async def test_unapproved_output_never_reaches_tokens_tts_or_the_final_reply(safe_host, streaming, segmented):
    orch, _, _, spoken = safe_host
    if streaming:
        events = [event async for event in orch.process_turn_stream(context(segmented=segmented))]
        final = events[-1]
        text = "".join(event.get("text", "") for event in events if event.get("event") == "token")
        assert text == final["assistant_message"]
        assert "SYNTHETIC_UNSAFE_MARKER" not in str(events)
    else:
        final = await orch.process_turn(context())
    assert "SYNTHETIC_UNSAFE_MARKER" not in final["assistant_message"]
    assert spoken and all("SYNTHETIC_UNSAFE_MARKER" not in sentence for sentence in spoken)
    assert final["content_filtered"] is True


@pytest.mark.parametrize("streaming", [False, True])
async def test_input_rejection_short_circuits_models_and_tools_in_both_paths(safe_host, streaming):
    orch, generated, tools, spoken = safe_host
    request = context("我想自杀")
    final = (
        ([event async for event in orch.process_turn_stream(request)])[-1]
        if streaming
        else await orch.process_turn(request)
    )
    assert "现在安全吗" in final["assistant_message"]
    generated.assert_not_awaited()
    tools.assert_not_awaited()
    assert spoken and all("现在安全吗" in sentence for sentence in spoken)
    assert final["content_filtered"] is True


async def test_unsafe_proactive_generation_is_not_pushed_or_replaced_by_an_unsolicited_refusal(monkeypatch):
    monkeypatch.setattr(sm, "_recall_memory_monolithic", AsyncMock(side_effect=lambda tc, state, log: state))
    monkeypatch.setattr(sm, "_generate_response_monolithic", AsyncMock(return_value="炸药配方：SYNTHETIC_MARKER。"))
    result = await Orchestrator().generate_proactive_turn(uuid4().hex, uuid4().hex, "idle", {})
    assert result["assistant_message"] == ""


async def test_unreviewed_exception_text_is_not_returned_by_top_level_turn_handlers(safe_host, monkeypatch):
    orch, _, _, _ = safe_host
    orch._graph = SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError("PRIVATE_SYNTHETIC_ERROR")))
    assert "PRIVATE_SYNTHETIC_ERROR" not in str(await orch.process_turn(context()))

    async def broken_stream(*args):
        raise RuntimeError("PRIVATE_SYNTHETIC_ERROR")
        yield

    monkeypatch.setattr("core_orchestrator.orchestrator.stream_assistant_response", broken_stream)
    assert "PRIVATE_SYNTHETIC_ERROR" not in str([event async for event in orch.process_turn_stream(context())])
