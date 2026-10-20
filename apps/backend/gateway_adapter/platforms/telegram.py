"""Telegram Bot API adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
import structlog

from .base import BasePlatformAdapter
from .http_delivery import request_json, valid_text

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
        if not self._token or not valid_text(content, 4096):
            return None
        payload: Dict[str, Any] = {
            "chat_id": user_id,
            "text": content,
            "link_preview_options": {"is_disabled": True},
        }
        if reply_to_message_id:
            try:
                identifier = int(reply_to_message_id)
            except (ValueError, TypeError):
                return None
            if identifier <= 0:
                return None
            payload["reply_parameters"] = {"message_id": identifier}
        response = await request_json(self._client, "POST", url, json=payload)
        data = response.data or {}
        result = data.get("result")
        if data.get("ok") is True and isinstance(result, dict):
            identifier = result.get("message_id")
            if isinstance(identifier, int) and not isinstance(identifier, bool) and identifier > 0:
                return str(identifier)
        self._logger.warning("telegram.delivery_unconfirmed", outcome=response.outcome, status=response.status)
        return None

    async def broadcast(self, user_id: str, content: str) -> Optional[str]:
        # Telegram has no native broadcast; just send to the user
        return await self.send_message(user_id, content)

    async def health_check(self) -> bool:
        if not self._token:
            return False
        response = await request_json(self._client, "GET", f"{self._base_url}/getMe")
        return (response.data or {}).get("ok") is True
