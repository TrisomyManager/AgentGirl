"""Discord webhook adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
import structlog

from .base import BasePlatformAdapter
from .http_delivery import request_json, valid_text

logger = structlog.get_logger(__name__)


class DiscordAdapter(BasePlatformAdapter):
    """Send messages via Discord webhooks."""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__("discord", config)
        self._webhook_url: str = config.get("webhook_url", "")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def send_message(
        self,
        user_id: str,
        content: str,
        media: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> Optional[str]:
        if not self._webhook_url or not valid_text(content, 2000):
            return None
        payload: Dict[str, Any] = {"content": content, "username": "Companion AI",
                                   "allowed_mentions": {"parse": [], "replied_user": False}}
        if media and media.get("image_url"):
            payload["embeds"] = [{"image": {"url": media["image_url"]}}]
        try:
            url = httpx.URL(self._webhook_url).copy_set_param("wait", "true")
        except httpx.InvalidURL:
            return None
        response = await request_json(self._client, "POST", url, json=payload)
        identifier = (response.data or {}).get("id")
        if isinstance(identifier, str) and identifier.isascii() and identifier.isdecimal():
            return identifier
        self._logger.warning("discord.delivery_unconfirmed", outcome=response.outcome, status=response.status)
        return None

    async def broadcast(self, user_id: str, content: str) -> None:
        await self.send_message(user_id, content)
