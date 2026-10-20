import asyncio
import json
import logging
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from gateway_adapter.api import SendRequest, send_message
from gateway_adapter.platforms.discord import DiscordAdapter
from gateway_adapter.platforms.telegram import TelegramAdapter
from shared_contracts import Platform


async def attach(adapter, handler):
    await adapter._client.aclose()
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_telegram_plain_text_reply_and_log_redaction(caplog):
    adapter = TelegramAdapter({"bot_token": "123:private-credential"})
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    await attach(adapter, handle)
    try:
        with caplog.at_level(logging.INFO, logger="httpx"):
            assert await adapter.send_message("99", "<未转义>&你好", reply_to_message_id="7") == "42"
        body = json.loads(requests[0].content)
        assert body["text"] == "<未转义>&你好" and "parse_mode" not in body
        assert body["reply_parameters"] == {"message_id": 7}
        assert "private-credential" not in caplog.text
        assert "HTTP Request" in caplog.text
    finally:
        await adapter._client.aclose()


async def test_discord_waits_for_real_id_preserves_thread_and_disables_mentions(caplog):
    adapter = DiscordAdapter({"webhook_url": "https://discord.com/api/webhooks/123/private-credential?thread_id=77"})
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "42"})

    await attach(adapter, handle)
    try:
        with caplog.at_level(logging.INFO, logger="httpx"):
            assert await adapter.send_message("owner", "@everyone hello") == "42"
        assert requests[0].url.params["thread_id"] == "77" and requests[0].url.params["wait"] == "true"
        assert json.loads(requests[0].content)["allowed_mentions"] == {"parse": [], "replied_user": False}
        assert "private-credential" not in caplog.text
        assert "HTTP Request" in caplog.text
    finally:
        await adapter._client.aclose()


@pytest.mark.parametrize("failure", ["timeout", "oversize", "malformed", "rate_limit"])
async def test_unconfirmed_sends_are_not_retried_or_logged_with_credentials(caplog, failure):
    adapter = TelegramAdapter({"bot_token": "123:private-credential"})
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        if failure == "timeout":
            raise httpx.ReadTimeout(str(request.url))
        if failure == "oversize":
            return httpx.Response(200, content=b"x" * 65537)
        if failure == "rate_limit":
            return httpx.Response(429, json={"description": "private-credential", "parameters": {"retry_after": 10}})
        return httpx.Response(200, content=b"not-json")

    await attach(adapter, handle)
    try:
        with caplog.at_level(logging.INFO, logger="httpx"):
            assert await adapter.send_message("99", "message") is None
        assert calls == 1 and "private-credential" not in caplog.text
    finally:
        await adapter._client.aclose()


async def test_send_cancellation_propagates_without_retry():
    adapter = TelegramAdapter({"bot_token": "123:synthetic"})
    entered = asyncio.Event()
    calls = 0

    async def handle(request):
        nonlocal calls
        calls += 1
        entered.set()
        await asyncio.Event().wait()

    await attach(adapter, handle)
    task = asyncio.create_task(adapter.send_message("99", "message"))
    try:
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert calls == 1
    finally:
        await adapter._client.aclose()


async def test_invalid_text_does_not_call_provider():
    adapter = TelegramAdapter({"bot_token": "123:synthetic"})
    requests = []
    await attach(adapter, lambda request: requests.append(request))
    try:
        assert await adapter.send_message("99", "\ud800") is None
        assert await adapter.send_message("99", "😀" * 2049) is None
        assert not requests
    finally:
        await adapter._client.aclose()


async def test_gateway_does_not_claim_delivery_without_platform_receipt():
    adapter = AsyncMock()
    adapter.send_message.return_value = None
    with pytest.raises(HTTPException) as error:
        await send_message(
            SendRequest(user_id="owner", platform="telegram", content="test"), {Platform.TELEGRAM: adapter}
        )
    assert error.value.status_code == 502
    adapter.send_message.assert_awaited_once()


async def test_legacy_broadcast_exposes_partial_confirmation_and_does_not_retry():
    from gateway_adapter.api import BroadcastRequest, broadcast_message

    confirmed, unconfirmed = AsyncMock(), AsyncMock()
    confirmed.broadcast.return_value = "real-receipt"
    unconfirmed.broadcast.return_value = None
    response = await broadcast_message(
        BroadcastRequest(user_id="owner", content="synthetic"),
        {Platform.TELEGRAM: confirmed, Platform.DISCORD: unconfirmed},
    )
    assert response.status_code == 502
    assert json.loads(response.body) == {"success": False, "sent_to": ["telegram"], "unconfirmed": ["discord"]}
    confirmed.broadcast.assert_awaited_once()
    unconfirmed.broadcast.assert_awaited_once()


async def test_telegram_broadcast_returns_actual_confirmation():
    adapter = TelegramAdapter({"bot_token": "123:synthetic"})
    await attach(adapter, lambda _: httpx.Response(200, json={"ok": True, "result": {"message_id": 90}}))
    try:
        assert await adapter.broadcast("22", "synthetic") == "90"
    finally:
        await adapter._client.aclose()
