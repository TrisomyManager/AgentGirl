import base64
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gateway_adapter.platforms.incoming import discord_message, qq_message, telegram_message
from shared_contracts import PlatformMessage


def test_telegram_uses_authenticated_sender_and_chat_not_claimed_internal_identity():
    update = {
        "update_id": 12,
        "user_id": "admin",
        "message": {
            "message_id": 7,
            "from": {"id": 99},
            "chat": {"id": -1001, "type": "supergroup"},
            "text": "message",
            "message_thread_id": 8,
            "forward_origin": {"type": "hidden_user"},
            "reply_to_message": {"text": "private quoted text"},
        },
    }
    message = telegram_message(update, "account")
    assert message.actor_id == "99" and message.conversation_id == "-1001"
    assert message.audience == "room" and message.thread_id == "8" and message.forwarded
    assert message.text == "message" and "user_id" not in message.model_dump()
    with pytest.raises(ValidationError):
        PlatformMessage(**message.model_dump(), user_id="admin")


@pytest.mark.parametrize(
    "update",
    [
        {"update_id": 1, "edited_message": {"text": "edit"}},
        {
            "update_id": 1,
            "message": {
                "from": {"id": 99, "is_bot": True},
                "chat": {"id": 99, "type": "private"},
                "message_id": 7,
                "text": "loop",
            },
        },
        {
            "update_id": 1,
            "message": {"from": {"id": True}, "chat": {"id": 99, "type": "private"}, "message_id": 7, "text": "bad ID"},
        },
        {"update_id": 1, "message": {"from": {"id": 99}, "chat": {"id": 99, "type": "private"}, "message_id": 7}},
    ],
)
def test_telegram_does_not_infer_senders_or_process_bot_loops_and_unsupported_events(update):
    assert telegram_message(update, "account") is None


def test_telegram_mentions_use_utf16_offsets_and_exact_bot_identity():
    message = {
        "update_id": 1,
        "message": {
            "message_id": 2,
            "from": {"id": 99},
            "chat": {"id": -1001, "type": "supergroup"},
            "text": "😀 @MyBot hello",
            "entities": [{"type": "mention", "offset": 3, "length": 6}],
        },
    }
    assert telegram_message(message, "account", bot_username="mybot").mentions_bot
    assert not telegram_message(message, "account", bot_username="anotherbot").mentions_bot


def test_discord_message_marks_room_mentions_and_ignores_webhook_bots():
    payload = {
        "op": 0,
        "t": "MESSAGE_CREATE",
        "d": {
            "id": "10",
            "author": {"id": "99"},
            "channel_id": "100",
            "guild_id": "200",
            "content": "hello",
            "mentions": [{"id": "bot"}],
        },
    }
    message = discord_message(payload, "account", bot_id="bot")
    assert message.audience == "room" and message.mentions_bot and message.actor_id == "99"
    payload["d"]["webhook_id"] = "300"
    assert discord_message(payload, "account", bot_id="bot") is None


def test_qq_c2c_and_group_targets_are_distinct_and_never_an_internal_owner():
    private = qq_message(
        {
            "op": 0,
            "t": "C2C_MESSAGE_CREATE",
            "id": "event",
            "d": {"id": "message", "content": "hello", "author": {"user_openid": "openid"}, "user_id": "admin"},
        },
        "account",
    )
    assert private.actor_id == private.conversation_id == "openid" and private.audience == "private"
    room = qq_message(
        {
            "op": 0,
            "t": "GROUP_AT_MESSAGE_CREATE",
            "id": "event",
            "d": {"id": "message", "content": "hello", "author": {"member_openid": "openid"}, "group_openid": "room"},
        },
        "account",
    )
    assert room.actor_id == "openid" and room.conversation_id == "room" and room.mentions_bot
    assert room.audience == "room"


def test_qq_signature_matches_official_go_sdk_vector_and_rejects_tampering():
    pytest.importorskip("cryptography")
    from gateway_adapter.platforms.qq_signature import QQSignature

    vector = json.loads((Path(__file__).parent / "data/qq_signature_vector.json").read_text())
    body = base64.b64decode(vector["body_base64"])
    signer = QQSignature(vector["synthetic_secret"])
    now = int(vector["timestamp"])
    assert signer.verify(body, vector["signature"], vector["timestamp"], now=now)
    assert not signer.verify(body + b" ", vector["signature"], vector["timestamp"], now=now)
    assert not signer.verify(body, vector["signature"], vector["timestamp"], now=now + 301)
    assert not signer.verify(body, "not-hex", vector["timestamp"], now=now)


def test_qq_challenge_is_a_signature_of_timestamp_and_exact_token():
    pytest.importorskip("cryptography")
    from gateway_adapter.platforms.qq_signature import QQSignature

    signer = QQSignature("synthetic-test-secret")
    response = signer.challenge({"op": 13, "d": {"plain_token": "original-token", "event_ts": "1728981195"}})
    assert response["plain_token"] == "original-token"
    assert signer.verify(b"original-token", response["signature"], "1728981195", now=1728981195)
