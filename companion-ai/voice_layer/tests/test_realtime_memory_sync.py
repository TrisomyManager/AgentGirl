"""Tests for realtime voice → memory scheduling helper."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from voice_layer.realtime_memory_sync import schedule_realtime_turn_memory_sync


@pytest.mark.asyncio
async def test_schedule_skips_empty_user_message() -> None:
    with patch("asyncio.create_task") as mock_ct:
        schedule_realtime_turn_memory_sync(
            user_id="u1",
            session_id="s1",
            user_message="   ",
            assistant_message="hello",
        )
    mock_ct.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_skips_empty_assistant() -> None:
    with patch("asyncio.create_task") as mock_ct:
        schedule_realtime_turn_memory_sync(
            user_id="u1",
            session_id="s1",
            user_message="hi",
            assistant_message="",
        )
    mock_ct.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_runs_sync_in_background() -> None:
    gate = asyncio.Event()

    async def fake_sync(*_a, **_k):
        gate.set()

    with patch(
        "core_orchestrator.state_machine.sync_completed_turn_to_memory",
        new=AsyncMock(side_effect=fake_sync),
    ):
        schedule_realtime_turn_memory_sync(
            user_id="u1",
            session_id="s1",
            user_message="你好",
            assistant_message="我在呢",
        )
        await asyncio.wait_for(gate.wait(), timeout=2.0)
