"""Tests for realtime voice → memory scheduling helper."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from voice_layer.realtime_memory_sync import (
    drain_memory_sync,
    schedule_realtime_turn_memory_sync,
    set_memory_sync_handler,
)


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

    set_memory_sync_handler(AsyncMock(side_effect=fake_sync))
    try:
        schedule_realtime_turn_memory_sync(
            user_id="u1",
            session_id="s1",
            user_message="你好",
            assistant_message="我在呢",
        )
        await asyncio.wait_for(gate.wait(), timeout=2.0)
    finally:
        set_memory_sync_handler(None)


async def test_voice_commits_are_ordered_per_session_without_blocking_other_users():
    entered, release, other_done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    order = []

    async def handler(**data):
        if data["user_message"] == "first":
            entered.set()
            await release.wait()
        order.append(data["user_message"])
        if data["user_id"] == "other":
            other_done.set()

    set_memory_sync_handler(handler)
    try:
        for user, message in [("u", "first"), ("u", "second"), ("other", "independent")]:
            schedule_realtime_turn_memory_sync(
                user_id=user, session_id="s", user_message=message, assistant_message="ok",
            )
        await entered.wait()
        await asyncio.wait_for(other_done.wait(), 1)
        assert order == ["independent"]
        release.set()
        await drain_memory_sync()
        assert order == ["independent", "first", "second"]
    finally:
        release.set()
        set_memory_sync_handler(None)


async def test_cancelling_a_reader_does_not_cancel_a_completed_voice_turn_commit():
    entered, release = asyncio.Event(), asyncio.Event()
    committed = []

    async def handler(**data):
        entered.set()
        await release.wait()
        committed.append(True)

    set_memory_sync_handler(handler)
    try:
        schedule_realtime_turn_memory_sync(user_id="u", session_id="s", user_message="hello", assistant_message="ok")
        await entered.wait()
        reader = asyncio.create_task(drain_memory_sync(user_id="u", session_id="s"))
        await asyncio.sleep(0)
        reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader
        release.set()
        await drain_memory_sync()
        assert committed == [True]
    finally:
        release.set()
        set_memory_sync_handler(None)
