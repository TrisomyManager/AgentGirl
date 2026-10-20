"""E2E tests for safety_guard input/output dual BLOCK paths through the state machine."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from core_orchestrator.state_machine import (
    build_graph,
    build_initial_state,
)
from safety_guard import default_guard, safe_fallback_reply


@pytest.fixture(autouse=True)
async def offline_host(monkeypatch):
    from main import create_app
    from shared_runtime.config import get_settings
    from shared_runtime.database import init_database_schema
    from core_orchestrator import state_machine

    create_app()
    await init_database_schema()
    monkeypatch.setattr(get_settings(), 'enable_memory_pipeline', False)

    async def skip_recall(state):
        return state

    # These tests exercise graph safety ordering; memory retrieval has its own integration suite.
    monkeypatch.setattr(state_machine, 'node_recall_memory', skip_recall)
from shared_contracts.models import Platform, TurnContext, UserProfile


@pytest.fixture(autouse=True)
def _monolithic_mode() -> None:
    with patch("core_orchestrator.state_machine._is_monolithic", return_value=True):
        yield


@pytest.fixture
def safety_test_user() -> UserProfile:
    return UserProfile(
        user_id="safety-e2e-user",
        display_name="Safety Tester",
        platform=Platform.APP,
        language="zh-CN",
    )


@pytest.fixture
def blocked_input_context(safety_test_user: UserProfile) -> TurnContext:
    return TurnContext(
        turn_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user=safety_test_user,
        user_message="我想自杀",
        platform=Platform.APP,
        has_voice=False,
    )


@pytest.fixture
def clean_input_context(safety_test_user: UserProfile) -> TurnContext:
    return TurnContext(
        turn_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user=safety_test_user,
        user_message="你好呀",
        platform=Platform.APP,
        has_voice=False,
    )


@pytest.mark.asyncio
async def test_input_block_short_circuits_llm(blocked_input_context: TurnContext) -> None:
    """When user input hits a BLOCK term, the state machine must short-circuit
    and return the safe fallback reply without calling the LLM."""
    graph = build_graph()
    initial_state = build_initial_state(blocked_input_context)
    final_state = await graph.ainvoke(initial_state)

    assistant_msg = final_state.get("assistant_message") or ""
    assert assistant_msg, "assistant_message must not be empty after input block"

    fallback = safe_fallback_reply(default_guard.check_input(blocked_input_context.user_message))
    assert assistant_msg == fallback, f"Expected safe fallback, got: {assistant_msg!r}"

    assert final_state.get("intent") == "chat"
    assert final_state.get("error") is None
    assert final_state.get("skip_action") is True


@pytest.mark.asyncio
async def test_output_block_replaces_unsafe_content(clean_input_context: TurnContext) -> None:
    """When the LLM returns content containing a BLOCK term, the output safety
    check must replace it with the safe fallback reply."""
    blocked_output = "这是包含自杀相关的不安全内容"

    graph = build_graph()
    initial_state = build_initial_state(clean_input_context)

    with patch(
        "core_orchestrator.state_machine._generate_response_monolithic",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.return_value = blocked_output
        final_state = await graph.ainvoke(initial_state)

    assistant_msg = final_state.get("assistant_message") or ""
    assert assistant_msg, "assistant_message must not be empty"

    assert assistant_msg != blocked_output, (
        "Blocked output must be replaced, but found same content"
    )

    fallback = safe_fallback_reply("output_blocked")
    assert assistant_msg == fallback, f"Expected safe fallback, got: {assistant_msg!r}"

    assert final_state.get("error") is None


@pytest.mark.asyncio
async def test_clean_input_clean_output_passes_through(clean_input_context: TurnContext) -> None:
    """Clean input that produces clean output must pass through both safety
    checks without modification from the guard."""
    clean_output = "你好呀！我在呢，有什么想聊的？"

    graph = build_graph()
    initial_state = build_initial_state(clean_input_context)

    with patch(
        "core_orchestrator.state_machine._generate_response_monolithic",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.return_value = clean_output
        final_state = await graph.ainvoke(initial_state)

    assistant_msg = final_state.get("assistant_message") or ""
    assert assistant_msg == clean_output, (
        f"Clean output must pass through unchanged, got: {assistant_msg!r}"
    )
    assert final_state.get("error") is None
