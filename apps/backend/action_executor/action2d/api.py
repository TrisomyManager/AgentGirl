"""FastAPI router for action_executor.action2d (P2 物理搬迁完成 / V2.1).

Endpoints (mounted by ``action_executor.action2d.main`` or ``main.py``):

  - POST /action/generate  — Generate full ActionSequence
  - POST /action/lip_sync  — Generate lip sync keyframes only
  - GET  /action/templates — List available action templates

Originally at ``action_layer/api.py``; that path is now a deprecated shim.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from shared_contracts.models import ActionSequence, ActionType, EmotionTag

from action_executor.action2d.generator_2d import Action2DGenerator
from action_executor.action2d.lip_sync import LipSyncGenerator
from action_executor.action2d.router import ActionRouter
from action_executor.action2d.sequencer import ActionSequencer

logger = structlog.get_logger("action_executor.action2d.api")

router = APIRouter(prefix="/action", tags=["action"])

sequencer: ActionSequencer | None = None
router_instance: ActionRouter | None = None
lip_sync_generator: LipSyncGenerator | None = None


def _get_sequencer() -> ActionSequencer:
    if sequencer is None:
        raise RuntimeError("ActionSequencer not initialized")
    return sequencer


def _get_router() -> ActionRouter:
    if router_instance is None:
        raise RuntimeError("ActionRouter not initialized")
    return router_instance


def _get_lip_sync() -> LipSyncGenerator:
    if lip_sync_generator is None:
        raise RuntimeError("LipSyncGenerator not initialized")
    return lip_sync_generator


class ActionGenerateRequest(BaseModel):
    turn_id: str = Field(..., description="Conversation turn ID")
    emotion: EmotionTag = Field(default=EmotionTag.NEUTRAL)
    text: str | None = Field(default=None, description="Text content for lip sync")
    audio_duration_ms: int = Field(default=2000, ge=100)
    reference_image_url: str | None = Field(default=None)
    intent: str | None = Field(default=None, description="Intent for action routing")
    action_type: str | None = Field(default=None, description="Explicit action type override")


class LipSyncRequest(BaseModel):
    text: str = Field(..., description="Text to generate lip sync for")
    duration_ms: int = Field(..., ge=100, description="TTS audio duration in ms")
    fps: int = Field(default=12, ge=1, le=60)


@router.post("/generate", response_model=ActionSequence)
async def generate_action(request: ActionGenerateRequest) -> ActionSequence:
    logger.info(
        "api.generate",
        turn_id=request.turn_id,
        emotion=request.emotion.value,
        audio_duration_ms=request.audio_duration_ms,
    )

    action_type: ActionType | None = None
    if request.action_type:
        try:
            action_type = ActionType(request.action_type)
        except ValueError:
            logger.warning("api.generate.invalid_action_type", action_type=request.action_type)

    sequence = await _get_sequencer().build_sequence(
        turn_id=request.turn_id,
        action_type=action_type,
        emotion=request.emotion,
        text=request.text,
        audio_duration_ms=request.audio_duration_ms,
        reference_image_url=request.reference_image_url,
        intent=request.intent,
    )
    return sequence


@router.post("/lip_sync")
async def generate_lip_sync(request: LipSyncRequest) -> list[dict]:
    logger.info(
        "api.lip_sync",
        text_len=len(request.text),
        duration_ms=request.duration_ms,
        fps=request.fps,
    )
    return _get_lip_sync().generate(
        text=request.text,
        duration_ms=request.duration_ms,
        fps=request.fps,
    )


@router.get("/templates")
async def list_templates() -> list[dict]:
    logger.info("api.templates")
    return _get_router().list_templates()
