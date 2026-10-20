"""Host-injected conversation context; voice providers never import the host."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class VoiceConversationContext:
    system_prompt: str
    temperature: float = 0.7
    max_tokens: int = 512
    # Opaque host state, returned only to its persistence callback, never to clients.
    state: Any = field(default=None, repr=False)
    avatar_timeline: dict[str, Any] | None = None


_loader: Callable[..., Awaitable[VoiceConversationContext]] | None = None


def segment_presentation(context: VoiceConversationContext | None, turn_id: str, index: int) -> dict | None:
    """Forward only the host's public timeline; never expose opaque host state."""
    if context is None or context.avatar_timeline is None:
        return None
    return {**context.avatar_timeline, "turn_id": turn_id, "segment_seq": max(0, min(255, index))}


def set_conversation_context_loader(loader: Callable[..., Awaitable[VoiceConversationContext]] | None) -> None:
    global _loader
    _loader = loader


async def load_conversation_context(
    *, user_id: str, session_id: str, user_message: str = "", turn_id: str,
) -> VoiceConversationContext | None:
    """Bound preparation; standalone providers remain usable without a host."""
    loader = _loader
    if loader is None:
        return None
    try:
        async with asyncio.timeout(5):
            from voice_layer.realtime_memory_sync import drain_memory_sync

            await drain_memory_sync(user_id=user_id, session_id=session_id)
            context = await loader(
                user_id=user_id, session_id=session_id, user_message=user_message, turn_id=turn_id,
            )
        if not isinstance(context, VoiceConversationContext):
            raise TypeError("Invalid voice context")
        return context
    except Exception as exc:
        logger.warning("voice_context.unavailable", reason=type(exc).__name__)
        raise RuntimeError("暂时无法读取通话的人格与记忆，请稍后重试。") from exc
