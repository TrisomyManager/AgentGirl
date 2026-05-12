"""Discord webhook adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
import structlog

from .base import BasePlatformAdapter

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
        payload: Dict[str, Any] = {"content": content, "username": "Companion AI"}
        if media and media.get("image_url"):
            payload["embeds"] = [{"image": {"url": media["image_url"]}}]
        try:
            resp = await self._client.post(self._webhook_url, json=payload)
            resp.raise_for_status()
            # Discord webhooks do not return message ID easily; return a placeholder
            self._logger.info("discord.sent", user_id=user_id)
            return resp.headers.get("x-discord-message-id")
        except Exception:
            self._logger.exception("discord.send_failed", user_id=user_id)
        return None

    async def broadcast(self, user_id: str, content: str) -> None:
        await self.send_message(user_id, content)
