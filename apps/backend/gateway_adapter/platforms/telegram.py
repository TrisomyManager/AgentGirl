"""Telegram Bot API adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
import structlog

from .base import BasePlatformAdapter

logger = structlog.get_logger(__name__)


class TelegramAdapter(BasePlatformAdapter):
    """Send messages via Telegram Bot API."""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__("telegram", config)
        self._token: str = config.get("bot_token", "")
        self._base_url = f"https://api.telegram.org/bot{self._token}"
        self._client = httpx.AsyncClient(timeout=30.0)

    async def send_message(
        self,
        user_id: str,
        content: str,
        media: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> Optional[str]:
        url = f"{self._base_url}/sendMessage"
        payload: Dict[str, Any] = {
            "chat_id": user_id,
            "text": content,
            "parse_mode": "HTML",
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = int(reply_to_message_id)
        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                msg_id = str(data["result"]["message_id"])
                self._logger.info("telegram.sent", user_id=user_id, message_id=msg_id)
                return msg_id
            self._logger.warning("telegram.api_error", user_id=user_id, description=data.get("description"))
        except Exception:
            self._logger.exception("telegram.send_failed", user_id=user_id)
        return None

    async def broadcast(self, user_id: str, content: str) -> None:
        # Telegram has no native broadcast; just send to the user
        await self.send_message(user_id, content)

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/getMe")
            return resp.status_code == 200 and resp.json().get("ok")
        except Exception:
            return False
