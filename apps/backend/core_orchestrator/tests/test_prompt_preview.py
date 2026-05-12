"""Tests for POST /orchestrator/debug/prompt_preview."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_prompt_preview_returns_long_system_prompt() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/orchestrator/debug/prompt_preview",
            json={
                "session_id": "preview-session",
                "user": {"user_id": "preview-user"},
                "user_message": "我叫小明，我喜欢喝热可可",
                "platform": "app",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "preview-session"
    assert data["user_id"] == "preview-user"
    prompt = data["system_prompt"]
    assert isinstance(prompt, str)
    assert len(prompt) > 200
    assert data["prompt_length"] == len(prompt)
