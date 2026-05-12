"""Async memory sync for completed realtime voice turns (fire-and-forget)."""

from __future__ import annotations

import asyncio
import uuid

import structlog

logger = structlog.get_logger("voice_layer.realtime_memory_sync")

# Stable channel tag for long-term / pipeline metadata (align with product wording).
REALTIME_MEMORY_CHANNEL = "voice_call"


def schedule_realtime_turn_memory_sync(
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_message: str,
    memory_channel: str = REALTIME_MEMORY_CHANNEL,
) -> None:
    """Queue a background task; never raises to callers."""
    text_u = (user_message or "").strip()
    text_a = (assistant_message or "").strip()
    if not text_u or not text_a:
        return

    async def _run() -> None:
        try:
            from core_orchestrator.state_machine import (
                build_minimal_memory_sync_state,
                sync_completed_turn_to_memory,
            )
            from shared_contracts.models import Platform, TurnContext, UserProfile

            tc = TurnContext(
                turn_id=str(uuid.uuid4()),
                session_id=session_id,
                user=UserProfile(user_id=user_id.strip() or "anonymous", platform=Platform.APP),
                user_message=text_u,
                platform=Platform.APP,
                has_voice=True,
            )
            state = build_minimal_memory_sync_state(
                tc,
                assistant_message=text_a,
                emotion_state=None,
                relationship_metrics=None,
                intent=None,
            )
            await sync_completed_turn_to_memory(
                turn_context=tc,
                orchestration_state=state,
                memory_channel=memory_channel,
            )
        except Exception as exc:
            logger.warning("realtime_memory_sync_failed", error=str(exc))

    try:
        asyncio.create_task(_run())
    except Exception as exc:
        logger.warning("realtime_memory_sync_schedule_failed", error=str(exc))
