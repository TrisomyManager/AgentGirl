"""Tests for the streaming turn pipeline.

Covers:
  - shared.llm_client.chunk_text_stream: chunks short text without losing chars.
  - core_orchestrator.state_machine.stream_assistant_response: emits the
    expected event sequence (meta → token+ → done) end-to-end in monolithic
    mode, with the rule-based fallback so no real LLM key is required.
  - POST /orchestrator/turn/stream: returns text/event-stream and emits the
    same event sequence on the wire.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import List

import pytest

# Force monolithic mode so the state machine takes the in-process LLM path
# and the rule-based fallback can drive the SSE pipeline without a real key.
# We deliberately DO NOT touch the other COMPANION_* feature flags here — the
# project-wide conftest.py sets COMPANION_LITE_MODE, and tweaking unrelated
# flags at module-import time would leak into other test files (e.g.
# memory_system tests that rely on the default enable_knowledge_graph value).
os.environ["COMPANION_MONOLITHIC"] = "true"

from fastapi.testclient import TestClient

from core_orchestrator.state_machine import stream_assistant_response
from shared.config import get_settings
from shared.llm_client import chunk_text_stream
from shared.models import Platform, TurnContext, UserProfile

get_settings.cache_clear()


@pytest.mark.asyncio
async def test_chunk_text_stream_preserves_content() -> None:
    chunks: List[str] = []
    async for chunk in chunk_text_stream("你好世界，这是一段测试。", chunk_size=4, delay_seconds=0):
        chunks.append(chunk)
    assert "".join(chunks) == "你好世界，这是一段测试。"
    assert len(chunks) >= 2  # actually got chunked, not one shot


@pytest.mark.asyncio
async def test_chunk_text_stream_empty_input_yields_nothing() -> None:
    chunks: List[str] = []
    async for chunk in chunk_text_stream("", chunk_size=4, delay_seconds=0):
        chunks.append(chunk)
    assert chunks == []


def _sample_turn_context(message: str = "你好呀") -> TurnContext:
    return TurnContext(
        turn_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user=UserProfile(
            user_id="stream-user-1",
            display_name="测试用户",
            platform=Platform.APP,
            language="zh-CN",
        ),
        user_message=message,
        platform=Platform.APP,
        has_voice=False,
    )


@pytest.mark.asyncio
async def test_stream_assistant_response_emits_meta_token_done() -> None:
    """End-to-end smoke test of the streaming pipeline in monolithic mode.

    Without a configured LLM provider the rule-based fallback kicks in, but
    chunk_text_stream still slices the reply into many token frames so we
    can assert the wire-level event order.
    """
    tc = _sample_turn_context("你好呀")
    events = []
    async for event in stream_assistant_response(tc):
        events.append(event)

    assert events, "stream_assistant_response yielded nothing"

    event_types = [e.get("event") for e in events]
    assert event_types[0] == "meta", f"expected meta first, got {event_types[:3]}"
    assert event_types[-1] == "done", f"expected done last, got {event_types[-3:]}"
    assert event_types.count("token") >= 1, "no token events emitted"

    full_text = "".join(
        e.get("text", "") for e in events if e.get("event") == "token"
    )
    assert full_text.strip(), "tokens concatenated to empty string"

    done_evt = events[-1]
    assert "_state" in done_evt, "done event missing _state for orchestrator"
    state = done_evt["_state"]
    assert state.get("assistant_message") == full_text, (
        "assistant_message in final state must equal concatenated tokens"
    )


def _build_test_client() -> TestClient:
    # Import here so the env vars set above are picked up by main.py
    from main import app

    return TestClient(app)


def test_turn_stream_endpoint_returns_event_stream() -> None:
    client = _build_test_client()
    payload = {
        "session_id": str(uuid.uuid4()),
        "user": {
            "user_id": "stream-http-user",
            "display_name": "测试",
            "platform": "app",
            "language": "zh-CN",
        },
        "user_message": "你好呀",
        "platform": "app",
        "has_voice": False,
        "request_voice_reply": False,
    }

    with client.stream("POST", "/orchestrator/turn/stream", json=payload) as resp:
        assert resp.status_code == 200, resp.read()
        assert "text/event-stream" in resp.headers.get("content-type", "")

        body = b"".join(resp.iter_bytes())

    text = body.decode("utf-8")
    assert "event: meta" in text
    assert "event: token" in text
    assert "event: done" in text

    # All data: lines must parse as JSON.
    for line in text.splitlines():
        if line.startswith("data:"):
            data_part = line[len("data:"):].strip()
            if not data_part:
                continue
            json.loads(data_part)
