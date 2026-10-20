"""Text-only bot delivery to an already bound conversation; no destination tools."""

import asyncio
import re
import time
from dataclasses import dataclass
from urllib.parse import quote

from .platforms.http_delivery import request_json


@dataclass(frozen=True)
class DeliveryReceipt:
    outcome: str
    message_id: str | None = None
    retry_after: float | None = None


def split_text(text, platform, *, max_parts=4):
    # QQ uses a conservative text ceiling; passive reply count is also bounded.
    limit = {"telegram": 4000, "discord": 1900, "qq": 300}[platform]
    if not isinstance(text, str) or not text:
        return []
    try:
        text.encode("utf-8")
    except UnicodeError:
        raise ValueError("Invalid reply text") from None
    if len(text) > limit * max_parts:
        raise ValueError("Reply exceeds platform limit")
    parts, current, length = [], [], 0
    for character in text:
        units = 2 if ord(character) > 0xFFFF else 1
        if length + units > limit:
            parts.append("".join(current))
            current, length = [], 0
        current.append(character)
        length += units
    if current:
        parts.append("".join(current))
    if len(parts) > max_parts:
        raise ValueError("Reply exceeds platform limit")
    return parts


class BotDelivery:
    def __init__(self, client):
        self.client = client
        self._qq_tokens = {}
        self._account_after = {}
        self._target_after = {}

    async def send(self, account, message, text, sequence):
        key = account.identity_key()
        target = (key, message.conversation_id)
        delay = max(self._account_after.get(key, 0), self._target_after.get(target, 0)) - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self._account_after[key] = time.monotonic() + 0.05
        self._target_after[target] = time.monotonic() + 1.1
        receipt = await self._send(account, message, text, sequence)
        if receipt.retry_after is not None:
            self._account_after[key] = time.monotonic() + receipt.retry_after
        return receipt

    async def _send(self, account, message, text, sequence):
        platform = account.platform
        if platform == "telegram":
            if not re.fullmatch(r"-?[0-9]{1,32}", message.conversation_id) or not message.message_id.isdecimal():
                return DeliveryReceipt("rejected")
            payload = {
                "chat_id": message.conversation_id,
                "text": text,
                "link_preview_options": {"is_disabled": True},
                "reply_parameters": {"message_id": int(message.message_id)},
            }
            if message.thread_id:
                if not message.thread_id.isdecimal():
                    return DeliveryReceipt("rejected")
                payload["message_thread_id"] = int(message.thread_id)
            response = await request_json(
                self.client,
                "POST",
                f"https://api.telegram.org/bot{account.token.get_secret_value()}/sendMessage",
                json=payload,
            )
            data = response.data or {}
            identifier = (data.get("result") or {}).get("message_id") if isinstance(data.get("result"), dict) else None
            if data.get("ok") is True and type(identifier) is int and identifier > 0:
                return DeliveryReceipt("confirmed", str(identifier))
            return DeliveryReceipt(
                "rejected" if data.get("ok") is False else _failure(response), retry_after=response.retry_after
            )
        if platform == "discord":
            if not re.fullmatch(r"[0-9]{1,32}", message.conversation_id) or not message.message_id.isdecimal():
                return DeliveryReceipt("rejected")
            response = await request_json(
                self.client,
                "POST",
                f"https://discord.com/api/v10/channels/{message.conversation_id}/messages",
                headers={"Authorization": "Bot " + account.token.get_secret_value()},
                json={
                    "content": text,
                    "allowed_mentions": {"parse": [], "replied_user": False},
                    "message_reference": {"message_id": message.message_id, "fail_if_not_exists": True},
                },
            )
        else:
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", message.conversation_id):
                return DeliveryReceipt("rejected")
            key = account.fingerprint()
            token, expiry = self._qq_tokens.get(key, (None, 0))
            if not token or expiry <= time.monotonic():
                response = await request_json(
                    self.client,
                    "POST",
                    "https://bots.qq.com/app/getAppAccessToken",
                    json={"appId": account.app_id, "clientSecret": account.secret.get_secret_value()},
                )
                data = response.data or {}
                token = data.get("access_token")
                try:
                    seconds = min(7200, max(0, int(data.get("expires_in", 0)) - 60))
                except (TypeError, ValueError, OverflowError):
                    seconds = 0
                if not isinstance(token, str) or not 1 <= len(token) <= 4096 or seconds <= 0:
                    return DeliveryReceipt("rejected")  # No message mutation was attempted.
                self._qq_tokens = {key: (token, time.monotonic() + seconds)}
            target_type = "users" if message.audience == "private" else "groups"
            response = await request_json(
                self.client,
                "POST",
                f"https://api.sgroup.qq.com/v2/{target_type}/{quote(message.conversation_id, safe='')}/messages",
                headers={"Authorization": "QQBot " + token, "X-Union-Appid": account.app_id},
                json={"content": text, "msg_type": 0, "msg_id": message.message_id, "msg_seq": sequence},
            )
        identifier = (response.data or {}).get("id")
        if response.outcome == "response" and isinstance(identifier, str) and 1 <= len(identifier) <= 256:
            return DeliveryReceipt("confirmed", identifier)
        return DeliveryReceipt(_failure(response), retry_after=response.retry_after)


def _failure(response):
    return "rejected" if response.outcome == "rejected" else "unknown"
