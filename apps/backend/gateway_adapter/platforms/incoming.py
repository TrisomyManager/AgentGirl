"""Parse authenticated provider payloads; internal ownership is bound by the host."""

from pydantic import ValidationError

from shared_contracts import PlatformMessage


def _identifier(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value) if str(value) else None


def telegram_message(update, account_id, *, bot_id=None, bot_username=None):
    if not isinstance(update, dict) or not isinstance(update.get("message"), dict):
        return None
    message = update["message"]
    actor, chat = message.get("from") or {}, message.get("chat") or {}
    if not isinstance(actor, dict) or not isinstance(chat, dict) or actor.get("is_bot") or message.get("sender_chat"):
        return None
    if chat.get("type") not in {"private", "group", "supergroup"}:
        return None
    mentioned = False
    text = message.get("text")
    entities = message.get("entities") or []
    if not isinstance(entities, list) or (isinstance(text, str) and len(text) > 16000):
        return None
    if isinstance(text, str):
        try:
            encoded = text.encode("utf-16-le")
        except UnicodeError:
            return None
        for entity in entities[:100]:
            if not isinstance(entity, dict):
                continue
            if entity.get("type") == "text_mention":
                target = entity.get("user") or {}
                mentioned |= bool(isinstance(target, dict) and bot_id and str(target.get("id")) == str(bot_id))
            if entity.get("type") in {"mention", "bot_command"} and bot_username:
                offset, length = entity.get("offset"), entity.get("length")
                if type(offset) is not int or type(length) is not int or offset < 0 or length <= 0:
                    continue
                if (offset + length) * 2 > len(encoded):
                    continue
                try:
                    span = encoded[offset * 2 : (offset + length) * 2].decode("utf-16-le")
                except UnicodeError:
                    continue
                expected = "@" + bot_username.lstrip("@").casefold()
                mentioned |= span.casefold() == expected or (
                    span.startswith("/") and span.casefold().endswith(expected)
                )
    try:
        return PlatformMessage(
            platform="telegram",
            account_id=account_id,
            event_id=_identifier(update.get("update_id")),
            message_id=_identifier(message.get("message_id")),
            actor_id=_identifier(actor.get("id")),
            conversation_id=_identifier(chat.get("id")),
            text=message.get("text"),
            audience="private" if chat["type"] == "private" else "room",
            mentions_bot=mentioned,
            thread_id=_identifier(message.get("message_thread_id")),
            forwarded=bool(message.get("forward_origin") or message.get("forward_date")),
        )
    except ValidationError:
        return None


def discord_message(dispatch, account_id, *, bot_id=None):
    if (
        not isinstance(dispatch, dict)
        or type(dispatch.get("op")) is not int
        or dispatch.get("op") != 0
        or dispatch.get("t") != "MESSAGE_CREATE"
    ):
        return None
    message = dispatch.get("d")
    if not isinstance(message, dict):
        return None
    actor = message.get("author") or {}
    if not isinstance(actor, dict) or actor.get("bot") or message.get("webhook_id"):
        return None
    mentions = message.get("mentions") or []
    if not isinstance(mentions, list):
        return None
    try:
        return PlatformMessage(
            platform="discord",
            account_id=account_id,
            event_id=_identifier(message.get("id")),
            message_id=_identifier(message.get("id")),
            actor_id=_identifier(actor.get("id")),
            conversation_id=_identifier(message.get("channel_id")),
            text=message.get("content"),
            audience="room" if message.get("guild_id") else "private",
            mentions_bot=bool(bot_id and any(isinstance(item, dict) and item.get("id") == bot_id for item in mentions)),
            forwarded=bool(message.get("message_snapshots")),
        )
    except ValidationError:
        return None


def qq_message(event, account_id):
    if not isinstance(event, dict) or type(event.get("op")) is not int or event.get("op") != 0:
        return None
    kind, message = event.get("t"), event.get("d")
    if kind not in {"C2C_MESSAGE_CREATE", "GROUP_AT_MESSAGE_CREATE"} or not isinstance(message, dict):
        return None
    actor = message.get("author") or {}
    if not isinstance(actor, dict) or actor.get("bot"):
        return None
    private = kind == "C2C_MESSAGE_CREATE"
    sender = actor.get("user_openid") if private else actor.get("member_openid")
    try:
        return PlatformMessage(
            platform="qq",
            account_id=account_id,
            event_id=_identifier(event.get("id") or message.get("id")),
            message_id=_identifier(message.get("id")),
            actor_id=_identifier(sender),
            conversation_id=_identifier(sender if private else message.get("group_openid")),
            text=message.get("content"),
            audience="private" if private else "room",
            mentions_bot=not private,
        )
    except ValidationError:
        return None
