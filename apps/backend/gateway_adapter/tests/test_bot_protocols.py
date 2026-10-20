"""Signed callbacks and actual request contracts, without external messages."""

import asyncio
import json
import socket
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from gateway_adapter.callbacks import create_callback_app, serve_callbacks
from gateway_adapter.config import PlatformsConfig
from gateway_adapter.delivery import BotDelivery
from gateway_adapter.platforms.qq_signature import QQSignature
from gateway_adapter.receivers import discord_sdk_message
from gateway_adapter.store import InboxFullError
from shared_contracts import PlatformMessage


def configuration(platform):
    return PlatformsConfig.model_validate_json(
        json.dumps(
            {
                "enabled": True,
                "qq_callback_port": 9876,
                "accounts": [
                    {
                        "id": "testbot",
                        "platform": platform,
                        "enabled": True,
                        "receive": True,
                        "reply": True,
                        "token": "123:synthetic-token",
                        "app_id": "77",
                        "secret": "synthetic-secret",
                    }
                ],
                "bindings": [
                    {
                        "id": "test",
                        "account_id": "testbot",
                        "enabled": True,
                        "user_id": "synthetic-owner",
                        "actor_id": "11",
                        "conversation_id": "22",
                        "audience": "private",
                    }
                ],
            }
        )
    )


def message(platform):
    return PlatformMessage(
        platform=platform,
        account_id="testbot",
        event_id="1",
        message_id="7",
        actor_id="11",
        conversation_id="22",
        text="hi",
        audience="private",
    )


@pytest.mark.parametrize("platform", ["telegram", "discord", "qq"])
async def test_bound_bot_sends_to_original_target_and_requires_real_receipt(platform, caplog):
    config = configuration(platform)
    requests = []

    def provider(request):
        requests.append(request)
        if request.url.path.endswith("getAppAccessToken"):
            return httpx.Response(200, json={"access_token": "synthetic-access", "expires_in": "7200"})
        if platform == "telegram":
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 900}})
        return httpx.Response(200, json={"id": "900"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        delivery = BotDelivery(client)
        receipt = await delivery.send(config.accounts[0], message(platform), "@everyone <b>你好</b>", 1)
    assert receipt.outcome == "confirmed" and receipt.message_id == "900"
    payload = json.loads(requests[-1].content)
    assert "synthetic-token" not in caplog.text and "synthetic-access" not in caplog.text
    if platform == "telegram":
        assert payload["chat_id"] == "22" and payload["reply_parameters"] == {"message_id": 7}
        assert "parse_mode" not in payload
    elif platform == "discord":
        assert requests[-1].url.path == "/api/v10/channels/22/messages"
        assert payload["allowed_mentions"] == {"parse": [], "replied_user": False}
        assert payload["message_reference"]["message_id"] == "7"
    else:
        assert requests[-1].url.path == "/v2/users/22/messages"
        assert payload["msg_id"] == "7" and payload["msg_seq"] == 1
        assert requests[-1].headers["authorization"] == "QQBot synthetic-access"


@pytest.mark.parametrize("failure,status", [("timeout", "unknown"), ("server", "unknown"), ("rate", "rejected")])
async def test_bot_mutations_are_single_attempt_and_keep_uncertainty(failure, status):
    calls = []

    def provider(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic timeout")
        return httpx.Response(503 if failure == "server" else 429, json={"message": "synthetic-token"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        receipt = await BotDelivery(client).send(configuration("discord").accounts[0], message("discord"), "hi", 1)
    assert receipt.outcome == status and len(calls) == 1


async def test_telegram_thread_is_bound_and_invalid_target_does_not_make_request():
    requests = []

    def provider(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 90}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        bot = BotDelivery(client)
        account = configuration("telegram").accounts[0]
        assert (await bot.send(account, message("telegram").model_copy(update={"thread_id": "9"}), "hi", 1)).message_id
        assert (
            await bot.send(account, message("telegram").model_copy(update={"conversation_id": "../evil"}), "hi", 1)
        ).outcome == "rejected"
    assert len(requests) == 1 and json.loads(requests[0].content)["message_thread_id"] == 9


def signed_event(event):
    body = json.dumps(event).encode()
    timestamp = str(int(time.time()))
    signature = QQSignature("synthetic-secret")._key.sign(timestamp.encode() + body).hex()
    return body, {"x-signature-ed25519": signature, "x-signature-timestamp": timestamp}


def qq_runtime():
    return SimpleNamespace(config=lambda: configuration("qq"), accept=AsyncMock(return_value="accepted"))


async def test_qq_challenge_and_dispatch_authenticate_before_parsing_or_acceptance():
    runtime = qq_runtime()
    app = create_callback_app(runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://callback") as client:
        body, headers = signed_event({"op": 13, "d": {"plain_token": "challenge", "event_ts": "1234567890"}})
        rejected = await client.post("/qq/testbot", content=body)
        assert rejected.status_code == 401
        challenge = await client.post("/qq/testbot", content=body, headers=headers)
        assert challenge.status_code == 200
        result = challenge.json()
        QQSignature("synthetic-secret")._key.public_key().verify(
            bytes.fromhex(result["signature"]), b"1234567890challenge"
        )
        runtime.accept.assert_not_awaited()
        event = {
            "op": 0,
            "id": "event",
            "t": "C2C_MESSAGE_CREATE",
            "d": {
                "id": "7",
                "author": {"user_openid": "11"},
                "content": "hello",
                "user_id": "forged-owner",
            },
        }
        body, headers = signed_event(event)
        accepted = await client.post("/qq/testbot", content=body, headers=headers)
        assert accepted.status_code == 200 and accepted.json() == {"op": 12}
        incoming = runtime.accept.call_args.args[0]
        assert incoming.actor_id == "11" and incoming.conversation_id == "11" and not hasattr(incoming, "user_id")
        runtime.accept.side_effect = InboxFullError()
        assert (await client.post("/qq/testbot", content=body, headers=headers)).status_code == 503
        assert (await client.post("/qq/unknown", content=body, headers=headers)).status_code == 404
        assert (await client.get("/docs")).status_code == 404


async def test_callback_listener_uses_real_loopback_http_and_closes_port():
    reservation = socket.socket()
    reservation.bind(("127.0.0.1", 0))
    port = reservation.getsockname()[1]
    reservation.close()
    server, task, listener = await serve_callbacks(qq_runtime(), port)
    try:
        body, headers = signed_event({"op": 13, "d": {"plain_token": "live-loopback", "event_ts": "1234567890"}})
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(f"http://127.0.0.1:{port}/qq/testbot", content=body, headers=headers)
            assert response.status_code == 200 and response.json()["plain_token"] == "live-loopback"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 7)
        listener.close()
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_discord_sdk_conversion_keeps_the_public_boundary_and_discards_quoted_text():
    source = SimpleNamespace(
        id=7,
        channel=SimpleNamespace(id=22),
        guild=SimpleNamespace(id=33),
        author=SimpleNamespace(id=11, bot=False),
        webhook_id=None,
        content="<@77> hello",
        mentions=[SimpleNamespace(id=77)],
        message_snapshots=[],
    )
    parsed = discord_sdk_message(source, "testbot", 77)
    assert parsed.audience == "room" and parsed.mentions_bot
    assert parsed.conversation_id == "22" and parsed.text == "<@77> hello"
    source.message_snapshots = [object()]
    assert discord_sdk_message(source, "testbot", 77).forwarded
    source.author.bot = True
    assert discord_sdk_message(source, "testbot", 77) is None


async def test_actual_discord_sdk_receives_from_local_http_and_websocket(monkeypatch):
    """Exercise SDK login, heartbeat/identify and dispatch over real loopback sockets."""
    import discord
    from aiohttp import web
    from yarl import URL

    from gateway_adapter.receivers import discord_receiver

    config = configuration("discord")
    accepted = asyncio.Event()
    received = []
    identified = []
    bot = {"id": "77", "username": "SyntheticBot", "discriminator": "0000", "avatar": None, "bot": True}

    def discord_json(data):
        response = web.json_response(data)
        response.headers["Content-Type"] = "application/json"
        return response

    async def profile(_):
        return discord_json(bot)

    async def application(_):
        return discord_json(
            {
                "id": "77",
                "name": "Synthetic App",
                "description": "local test",
                "icon": None,
                "bot_public": False,
                "bot_require_code_grant": False,
                "owner": {**bot, "id": "11", "bot": False},
                "verify_key": "00" * 32,
                "flags": 0,
            }
        )

    async def gateway(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"op": 10, "d": {"heartbeat_interval": 1000}})
        async for item in ws:
            if item.type != web.WSMsgType.TEXT:
                continue
            data = json.loads(item.data)
            if data.get("op") == 1:
                await ws.send_json({"op": 11, "d": None})
            if data.get("op") == 2:
                identified.append(data["d"])
                await ws.send_json(
                    {
                        "op": 0,
                        "s": 1,
                        "t": "READY",
                        "d": {
                            "v": 10,
                            "user": bot,
                            "guilds": [],
                            "session_id": "synthetic-session",
                            "resume_gateway_url": str(request.url.with_scheme("ws").with_path("/gateway")),
                            "application": {"id": "77", "flags": 0},
                        },
                    }
                )
                payload = {
                    "id": "7",
                    "channel_id": "22",
                    "author": {**bot, "id": "11", "bot": False},
                    "content": "hello over real websocket",
                    "timestamp": "2026-10-20T00:00:00+00:00",
                    "edited_timestamp": None,
                    "tts": False,
                    "mention_everyone": False,
                    "mentions": [],
                    "mention_roles": [],
                    "attachments": [],
                    "embeds": [],
                    "pinned": False,
                    "type": 0,
                    "flags": 0,
                }
                await ws.send_json({"op": 0, "s": 2, "t": "MESSAGE_CREATE", "d": payload})
        return ws

    async def accept(message, **_):
        received.append(message)
        accepted.set()
        return "accepted"

    app = web.Application()
    app.router.add_get("/api/v10/users/@me", profile)
    app.router.add_get("/api/v10/oauth2/applications/@me", application)
    app.router.add_get("/gateway", gateway)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    monkeypatch.setattr(discord.http.Route, "BASE", f"http://127.0.0.1:{port}/api/v10")
    monkeypatch.setattr(discord.gateway.DiscordWebSocket, "DEFAULT_GATEWAY", URL(f"ws://127.0.0.1:{port}/gateway"))
    runtime = SimpleNamespace(config=lambda: config, accept=accept, receiver_states={})
    task = asyncio.create_task(discord_receiver(runtime, config.accounts[0]))
    try:
        await asyncio.wait_for(accepted.wait(), 5)
        assert identified and received[0].actor_id == "11" and received[0].audience == "private"
        assert received[0].text == "hello over real websocket"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runner.cleanup()
    assert not any("_delay_ready" in task.get_coro().__qualname__ for task in asyncio.all_tasks())
