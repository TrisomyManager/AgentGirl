"""WeChat API adapter (simplified)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
import structlog

from .base import BasePlatformAdapter

logger = structlog.get_logger(__name__)


class WeChatAdapter(BasePlatformAdapter):
    """Send messages via WeChat Work / Official Account API."""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__("wechat", config)
        self._corp_id: str = config.get("corp_id", "")
        self._agent_id: str = config.get("agent_id", "")
        self._secret: str = config.get("secret", "")
        self._base_url = "https://qyapi.weixin.qq.com/cgi-bin"
        self._client = httpx.AsyncClient(timeout=30.0)
        self._access_token: Optional[str] = None

    async def _get_access_token(self) -> Optional[str]:
        if self._access_token:
            return self._access_token
        url = f"{self._base_url}/gettoken"
        try:
            resp = await self._client.get(
                url, params={"corpid": self._corp_id, "corpsecret": self._secret}
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get("access_token")
            return self._access_token
        except Exception:
            self._logger.exception("wechat.token_failed")
            return None

    async def send_message(
        self,
        user_id: str,
        content: str,
        media: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[str] = None,
    ) -> Optional[str]:
        token = await self._get_access_token()
        if not token:
            return None
        url = f"{self._base_url}/message/send?access_token={token}"
        payload = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": self._agent_id,
            "text": {"content": content},
            "safe": 0,
        }
        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode") == 0:
                self._logger.info("wechat.sent", user_id=user_id)
                return data.get("msgid")
            self._logger.warning("wechat.api_error", errcode=data.get("errcode"), errmsg=data.get("errmsg"))
        except Exception:
            self._logger.exception("wechat.send_failed", user_id=user_id)
        return None

    async def broadcast(self, user_id: str, content: str) -> None:
        await self.send_message(user_id, content)
