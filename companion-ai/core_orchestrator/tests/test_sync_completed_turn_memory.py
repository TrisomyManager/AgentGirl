"""Tests for extracted sync_completed_turn_to_memory helper."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from core_orchestrator.state_machine import (
    build_minimal_memory_sync_state,
    sync_completed_turn_to_memory,
)
from shared_contracts.models import Platform, TurnContext, UserProfile


@pytest.mark.asyncio
async def test_sync_skips_whitespace_only_user_message() -> None:
    tc = TurnContext(
        turn_id=str(uuid.uuid4()),
        session_id="sess",
        user=UserProfile(user_id="u1", platform=Platform.APP),
        user_message="  \n\t  ",
        platform=Platform.APP,
    )
    state = build_minimal_memory_sync_state(tc, assistant_message="reply")

    with patch("memory_system.working.get_working_memory") as mock_gwm:
        await sync_completed_turn_to_memory(
            turn_context=tc,
            orchestration_state=state,
            memory_channel=None,
        )
    mock_gwm.assert_not_called()


@pytest.mark.asyncio
async def test_sync_observes_working_memory_when_user_non_empty() -> None:
    tc = TurnContext(
        turn_id=str(uuid.uuid4()),
        session_id="sess",
        user=UserProfile(user_id="u1", platform=Platform.APP),
        user_message="hello",
        platform=Platform.APP,
    )
    state = build_minimal_memory_sync_state(tc, assistant_message="hi there")

    mock_wm = AsyncMock()
    mock_wm.observe_turn = AsyncMock()

    with patch("memory_system.working.get_working_memory", return_value=mock_wm), patch(
        "core_orchestrator.state_machine._is_monolithic",
        return_value=False,
    ), patch("core_orchestrator.state_machine.get_settings") as mock_settings, patch(
        "core_orchestrator.state_machine.memory_client.post", new_callable=AsyncMock
    ):
        mock_settings.return_value.enable_memory_pipeline = False
        await sync_completed_turn_to_memory(
            turn_context=tc,
            orchestration_state=state,
            memory_channel=None,
        )

    mock_wm.observe_turn.assert_awaited_once()
    call_kw = mock_wm.observe_turn.await_args.kwargs
    assert call_kw["session_id"] == "sess"
    assert call_kw["user_message"] == "hello"
    assert call_kw["assistant_message"] == "hi there"
