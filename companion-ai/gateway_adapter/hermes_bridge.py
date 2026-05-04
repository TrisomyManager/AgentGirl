"""Bridge to Hermes gateway.

This module documents how the gateway_adapter integrates with the original
Hermes agent gateway, and provides a simplified multi-platform sender using
HTTP webhooks.

## Hermes Integration Notes

Hermes (`hermes-agent`) contains a `gateway/` directory with:
- `gateway/platforms/*` — platform-specific senders (Telegram, Discord, WeChat, etc.)
- `gateway/run.py` — session lifecycle and message routing loop
- `gateway/webhook.py` — webhook receivers for incoming platform events

The `gateway_adapter` conceptually reuses the platform adapter patterns from
Hermes but wraps them as an internal FastAPI service rather than a standalone
bot runner. The original Hermes `agent/` directory (memory, prompt building,
model routing) is intentionally NOT reused — those responsibilities have moved
to `core_orchestrator`, `memory_system`, and `persona_engine`.

### What we reuse from Hermes
- Adapter interface design: `send_message(user_id, content, media)`
- Webhook payload parsing conventions
- Session ID generation and continuity logic

### What we do NOT reuse
- Hermes `agent/run.py` turn loop
- Hermes `memory/` implementations
- Hermes `prompts/` templates

### Migration path
If Hermes platform adapters need to be imported directly, add `hermes-agent`
to PYTHONPATH and import from `gateway.platforms.telegram` etc. For this
implementation we provide standalone adapters to avoid the dependency.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class HermesBridge:
    """Simplified multi-platform sender using HTTP webhooks.

    In a full-Hermes deployment, this class would delegate to Hermes's
    native platform runners. Here we keep the interface stable and use
    the local platform adapters instead.
    """

    def __init__(self, webhook_base_url: Optional[str] = None) -> None:
        self._webhook_base_url = webhook_base_url or "http://localhost:8006"
        self._client = httpx.AsyncClient(timeout=30.0)

    async def send_to_platform(
        self,
        platform: str,
        user_id: str,
        content: str,
        media: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send a message to a specific platform via internal webhook.

        This is a convenience fallback when the adapter registry is unavailable.
        """
        url = f"{self._webhook_base_url}/gateway/send"
        payload = {
            "user_id": user_id,
            "platform": platform,
            "content": content,
            "media": media or {},
        }
        try:
            resp = await self._client.post(url, json=payload)
            return resp.status_code == 200
        except Exception:
            logger.exception("hermes_bridge.send_failed", platform=platform, user_id=user_id)
            return False

    async def broadcast(
        self,
        user_id: str,
        content: str,
        platforms: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """Broadcast to multiple platforms."""
        url = f"{self._webhook_base_url}/gateway/broadcast"
        payload = {
            "user_id": user_id,
            "content": content,
            "platforms": platforms or [],
        }
        try:
            resp = await self._client.post(url, json=payload)
            return resp.json().get("results", {})
        except Exception:
            logger.exception("hermes_bridge.broadcast_failed", user_id=user_id)
            return {}
