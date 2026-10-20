"""Lifecycle tests exercise actual SQL receipts, revocation and cancellation."""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from gateway_adapter.config import ConfigSource, PlatformConfigError
from gateway_adapter.delivery import DeliveryReceipt, split_text
from gateway_adapter.runtime import PlatformRuntime
from gateway_adapter.store import BindingORM, InboxORM, revoke_user_bindings
from shared_contracts import PlatformMessage
from shared_runtime.database import AsyncSessionLocal, Base, engine
from shared_runtime.user_lifecycle import erase_user_work


@pytest.fixture
async def environment(tmp_path):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    suffix = uuid4().hex[:12]
    data = {
        "enabled": True,
        "accounts": [
            {
                "id": "tg_" + suffix,
                "platform": "telegram",
                "enabled": True,
                "receive": True,
                "reply": True,
                "token": "123:synthetic",
            }
        ],
        "bindings": [
            {
                "id": "private",
                "account_id": "tg_" + suffix,
                "user_id": "platform_" + suffix,
                "actor_id": "11",
                "conversation_id": "22",
                "audience": "private",
                "enabled": True,
            }
        ],
    }
    path = tmp_path / "private.json"

    def save():
        path.write_text(json.dumps(data), encoding="utf-8")

    save()
    generate = AsyncMock(return_value="你好")
    delivery = AsyncMock()
    delivery.send.return_value = DeliveryReceipt("confirmed", "900")
    runtime = PlatformRuntime(source=ConfigSource(path), generate=generate, delivery=delivery)
    message = PlatformMessage(
        platform="telegram",
        account_id=data["accounts"][0]["id"],
        event_id="1",
        message_id="5",
        actor_id="11",
        conversation_id="22",
        text="你好",
        audience="private",
    )
    yield runtime, data, save, message
    await runtime.close()
    async with AsyncSessionLocal() as session:
        for model in (InboxORM, BindingORM):
            await session.execute(delete(model).where(model.user_id == data["bindings"][0]["user_id"]))
        await session.commit()


async def rows(runtime):
    async with runtime.store.sessions() as session:
        return list(
            (
                await session.scalars(
                    select(InboxORM)
                    .where(InboxORM.account_key == runtime.config().accounts[0].identity_key())
                    .order_by(InboxORM.created_at)
                )
            ).all()
        )


def test_old_tokens_do_not_enable_receivers(monkeypatch):
    monkeypatch.delenv("COMPANION_PLATFORMS_CONFIG_FILE", raising=False)
    monkeypatch.setenv("COMPANION_TELEGRAM_BOT_TOKEN", "123:synthetic")
    assert not ConfigSource.from_environment().load().enabled


@pytest.mark.parametrize(
    "value",
    [
        {"enabled": "true"},
        {"accounts": [{"id": "bot", "platform": "telegram", "token": "synthetic-secret", "user_id": "victim"}]},
        {"accounts": [{"id": "bot", "platform": "telegram", "enabled": True, "receive": True}]},
        {
            "bindings": [
                {
                    "id": "a",
                    "account_id": "missing",
                    "user_id": "owner",
                    "actor_id": "1",
                    "conversation_id": "2",
                    "audience": "private",
                }
            ]
        },
    ],
)
def test_config_fails_closed_without_echoing_credentials(tmp_path, value):
    path = tmp_path / "private.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PlatformConfigError) as error:
        ConfigSource(path).load()
    assert "synthetic-secret" not in str(error.value)


async def test_exact_binding_and_forwarded_messages_are_rejected(environment):
    runtime, _, _, message = environment
    for changes in (
        {"actor_id": "stranger"},
        {"conversation_id": "other"},
        {"thread_id": "other"},
        {"audience": "room", "mentions_bot": True},
        {"forwarded": True},
        {"account_id": "other"},
    ):
        assert await runtime.accept(message.model_copy(update=changes)) == "ignored"
    assert not await rows(runtime)
    runtime.generate.assert_not_called()


async def test_durable_dedupe_survives_new_runtime_and_changed_event_id(environment):
    runtime, _, _, message = environment
    results = await asyncio.gather(*(runtime.accept(message) for _ in range(12)))
    assert results.count("accepted") == 1 and results.count("duplicate") == 11
    assert await runtime.process_one()
    assert (await rows(runtime))[0].status == "sent"
    replacement = PlatformRuntime(
        source=runtime.source,
        store=runtime.store,
        generate=runtime.generate,
        delivery=runtime.delivery,
        client=runtime.client,
    )
    try:
        await replacement.store.recover()
        assert await replacement.accept(message.model_copy(update={"event_id": "second"})) == "duplicate"
        assert not await replacement.process_one()
    finally:
        await replacement.close()
    runtime.generate.assert_awaited_once()
    runtime.delivery.send.assert_awaited_once()


async def test_room_requires_mention_and_has_distinct_persistent_session(environment):
    runtime, data, save, message = environment
    room = {**data["bindings"][0], "id": "room", "audience": "room", "conversation_id": "33"}
    data["bindings"].append(room)
    save()
    room_message = message.model_copy(update={"audience": "room", "conversation_id": "33", "event_id": "2"})
    assert await runtime.accept(room_message) == "ignored"
    assert await runtime.accept(room_message.model_copy(update={"mentions_bot": True})) == "accepted"
    assert await runtime.accept(message) == "accepted"
    recorded = await rows(runtime)
    assert len({row.session_id for row in recorded}) == 2


@pytest.mark.parametrize("outcome", ["unknown", "rejected"])
async def test_unconfirmed_send_is_never_replayed(environment, outcome):
    runtime, _, _, message = environment
    runtime.delivery.send.return_value = DeliveryReceipt(outcome)
    await runtime.accept(message)
    await runtime.process_one()
    assert (await rows(runtime))[0].status == outcome
    await runtime.store.recover()
    assert not await runtime.process_one()
    assert await runtime.accept(message) == "duplicate"
    runtime.delivery.send.assert_awaited_once()


async def test_partial_delivery_retains_confirmed_ids_without_replaying_parts(environment):
    runtime, _, _, message = environment
    runtime.generate.return_value = "a" * 4001
    runtime.delivery.send.side_effect = [DeliveryReceipt("confirmed", "first"), DeliveryReceipt("unknown")]
    await runtime.accept(message)
    await runtime.process_one()
    row = (await rows(runtime))[0]
    assert row.status == "unknown" and json.loads(row.sent_ids_json) == ["first"]
    assert runtime.delivery.send.await_count == 2
    await runtime.store.recover()
    assert not await runtime.process_one()


@pytest.mark.parametrize("before,after", [("processing", "interrupted"), ("sending", "unknown")])
async def test_recovery_does_not_repeat_model_tools_or_external_mutations(environment, before, after):
    runtime, _, _, message = environment
    await runtime.accept(message)
    row = (await rows(runtime))[0]
    await runtime.store.transition(row.id, "pending", before)
    await runtime.store.recover()
    assert not await runtime.process_one()
    assert (await rows(runtime))[0].status == after
    runtime.generate.assert_not_called()
    runtime.delivery.send.assert_not_called()


async def test_generated_reply_can_deliver_after_restart_without_regeneration(environment):
    runtime, _, _, message = environment
    await runtime.accept(message)
    row = (await rows(runtime))[0]
    await runtime.store.transition(row.id, "pending", "generated", reply_text="saved reply")
    await runtime.store.recover()
    await runtime.process_one()
    assert (await rows(runtime))[0].status == "sent"
    runtime.generate.assert_not_called()
    assert runtime.delivery.send.call_args.args[2] == "saved reply"


@pytest.mark.parametrize("change", ["disable", "malformed", "remove"])
async def test_binding_revocation_cancels_inflight_generation(environment, change):
    runtime, data, save, message = environment
    entered, finished = asyncio.Event(), asyncio.Event()

    async def generate(*_):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    runtime.generate.side_effect = generate
    await runtime.accept(message)
    processing = asyncio.create_task(runtime.process_one())
    await asyncio.wait_for(entered.wait(), 2)
    if change == "disable":
        data["bindings"][0]["enabled"] = False
        save()
    elif change == "malformed":
        runtime.source.path.write_text("{broken", encoding="utf-8")
    else:
        runtime.source.path.unlink()
    await asyncio.wait_for(processing, 3)
    assert finished.is_set()
    runtime.delivery.send.assert_not_called()
    save()
    assert (await rows(runtime))[0].status == "interrupted"


async def test_erasure_cancels_work_and_old_binding_cannot_recreate_rows(environment):
    runtime, data, save, message = environment
    await runtime.register_config(runtime.config())
    entered = asyncio.Event()

    async def generate(*_):
        entered.set()
        await asyncio.Event().wait()

    runtime.generate.side_effect = generate
    await runtime.accept(message)
    processing = asyncio.create_task(runtime.process_one())
    await asyncio.wait_for(entered.wait(), 2)
    user_id = data["bindings"][0]["user_id"]
    async with erase_user_work(user_id):
        assert processing.done()
        async with AsyncSessionLocal() as session:
            await revoke_user_bindings(session, user_id, runtime.config())
            await session.execute(delete(InboxORM).where(InboxORM.user_id == user_id))
            await session.execute(delete(BindingORM).where(BindingORM.user_id == user_id))
            await session.commit()
    await processing
    assert not await rows(runtime)
    assert await runtime.accept(message.model_copy(update={"event_id": "new", "message_id": "6"})) == "revoked"
    # Secret rotation and toggling flags cannot silently restore erased permissions.
    data["accounts"][0]["token"] = "123:rotated"
    save()
    assert await runtime.accept(message) == "revoked"
    data["bindings"][0]["id"] = "reviewed-new-binding"
    save()
    assert await runtime.accept(message) == "accepted"
    runtime.delivery.send.assert_not_called()


def test_utf16_splitting_is_bounded_and_does_not_cut_surrogates():
    parts = split_text("😀" * 2001, "telegram")
    assert [len(part.encode("utf-16-le")) // 2 for part in parts] == [4000, 2]
    with pytest.raises(ValueError):
        split_text("x" * 1201, "qq")
    with pytest.raises(ValueError):
        split_text("bad\ud800", "discord")


async def test_telegram_cursor_advances_only_after_durable_acceptance(environment):
    from gateway_adapter.receivers import telegram_poll_once
    from gateway_adapter.store import InboxFullError

    runtime, _, _, message = environment
    captured = []

    def provider(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": [
                    {
                        "update_id": 40,
                        "message": {
                            "message_id": 5,
                            "from": {"id": 11},
                            "chat": {"id": 22, "type": "private"},
                            "text": "hi",
                        },
                    }
                ],
            },
        )

    account = runtime.config().accounts[0]
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        runtime.client = client
        await telegram_poll_once(runtime, account, bot_id="77", bot_username="bot")
        assert await runtime.store.cursor(account.identity_key()) == 40
        assert len(await rows(runtime)) == 1
        await runtime.store.advance(account.identity_key(), 39)
        assert await runtime.store.cursor(account.identity_key()) == 40
        # A different bot has no cursor; failure must leave its update unacknowledged.
        original = runtime.store.cursor
        runtime.store.cursor = AsyncMock(return_value=None)
        runtime.accept = AsyncMock(side_effect=InboxFullError())
        with pytest.raises(InboxFullError):
            await telegram_poll_once(runtime, account, bot_id="77", bot_username="bot")
        runtime.store.cursor = original
        assert await runtime.store.cursor(account.identity_key()) == 40
    assert "offset" not in captured[0]
