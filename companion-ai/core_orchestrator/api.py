"""FastAPI routers for core_orchestrator.

Endpoints:
  POST /orchestrator/turn    — Main entry point for processing a user turn
  POST /orchestrator/health  — Health check (module-level)
  GET  /orchestrator/status  — Show connected modules status
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from shared.models import (
    DeviceInfo,
    EmotionTag,
    Platform,
    TurnContext,
    UserProfile,
)

from core_orchestrator.orchestrator import get_orchestrator
from core_orchestrator.project_status import get_project_status, ProjectStatusData
from shared.llm_client import get_runtime_llm_config, update_runtime_llm_config, save_llm_config_to_disk
from shared.voice_runtime_config import (
    get_runtime_voice_config,
    update_runtime_voice_config,
    save_voice_config_to_disk,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class TurnRequest(BaseModel):
    """API request model for processing a single turn."""

    session_id: str
    user: UserProfile
    user_message: str
    platform: Platform = Platform.APP
    has_voice: bool = False
    voice_duration_ms: Optional[int] = None
    has_image: bool = False
    image_urls: List[str] = []
    device_info: Optional[DeviceInfo] = None


class TurnResponse(BaseModel):
    """API response model after processing a turn."""

    turn_id: str
    session_id: str
    user_id: str
    assistant_message: str
    emotion: Optional[Dict[str, Any]] = None
    voice_url: Optional[str] = None
    action_sequence: Optional[Dict[str, Any]] = None
    intent: Optional[str] = None
    intent_confidence: Optional[float] = None
    memory_entries_count: int = 0
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    timestamp: str


class ModuleStatus(BaseModel):
    """Status of a single downstream module."""

    service: str
    url: str
    status: str
    healthy: bool


class StatusResponse(BaseModel):
    """Aggregated status of all connected modules."""

    orchestrator: str
    modules: List[ModuleStatus]
    timestamp: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/turn",
    response_model=TurnResponse,
    status_code=status.HTTP_200_OK,
    summary="Process a single user turn",
)
async def process_turn(request: TurnRequest) -> TurnResponse:
    """Main entry point for processing a user turn.

    Accepts text or voice input, runs the full LangGraph state machine,
    and returns the assistant response with optional voice/action data.
    """
    turn_id = str(uuid.uuid4())
    log = logger.bind(turn_id=turn_id, session_id=request.session_id)
    log.info("api_turn_request", user_id=request.user.user_id, platform=request.platform.value)

    turn_context = TurnContext(
        turn_id=turn_id,
        session_id=request.session_id,
        user=request.user,
        user_message=request.user_message,
        platform=request.platform,
        has_voice=request.has_voice,
        voice_duration_ms=request.voice_duration_ms,
        has_image=request.has_image,
        image_urls=request.image_urls,
        device_info=request.device_info,
    )

    try:
        orch = await get_orchestrator()
        result = await orch.process_turn(turn_context)
    except Exception as exc:
        log.exception("api_turn_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Turn processing failed: {exc}",
        )

    return TurnResponse(**result)


@router.post(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Module-level health check",
)
async def module_health() -> HealthResponse:
    """Return a lightweight health check for load balancers."""
    return HealthResponse(
        status="healthy",
        service="core_orchestrator",
        timestamp=datetime.utcnow().isoformat(),
    )


@router.get(
    "/status",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Show connected modules status",
)
async def module_status() -> StatusResponse:
    """Query health of all downstream services and return aggregated status."""
    orch = await get_orchestrator()
    service_health = await orch.service_status()
    modules = [
        ModuleStatus(
            service=svc["service"],
            url=svc["url"],
            status=svc["status"],
            healthy=svc["healthy"],
        )
        for svc in service_health
    ]
    return StatusResponse(
        orchestrator="healthy",
        modules=modules,
        timestamp=datetime.utcnow().isoformat(),
    )


# ---------------------------------------------------------------------------
# LLM settings — read / update at runtime without restart
# ---------------------------------------------------------------------------


class LlmConfigRequest(BaseModel):
    provider: str = ""          # "openai" | "anthropic" | ""
    api_key: str = ""
    base_url: str = ""
    model: str = ""


class LlmConfigResponse(BaseModel):
    provider: str
    api_key_set: bool
    base_url: str
    model: str


@router.get(
    "/settings/llm",
    response_model=LlmConfigResponse,
    tags=["settings"],
    summary="Get current LLM config",
)
async def get_llm_settings() -> LlmConfigResponse:
    rt = get_runtime_llm_config()
    has_openai = bool(rt.get("openai_api_key"))
    has_anthropic = bool(rt.get("anthropic_api_key"))
    provider = rt.get("provider") or ("openai" if has_openai else ("anthropic" if has_anthropic else ""))
    return LlmConfigResponse(
        provider=provider,
        api_key_set=has_openai or has_anthropic,
        base_url=rt.get("openai_base_url") or rt.get("anthropic_base_url") or "",
        model=rt.get("default_model") or "",
    )


@router.post(
    "/settings/llm",
    response_model=LlmConfigResponse,
    tags=["settings"],
    summary="Update LLM config at runtime",
)
async def save_llm_settings(req: LlmConfigRequest) -> LlmConfigResponse:
    # Clear both providers first, then set the chosen one
    update_runtime_llm_config(openai_api_key="", anthropic_api_key="",
                               openai_base_url="", anthropic_base_url="", provider="")
    if req.provider == "openai":
        update_runtime_llm_config(
            provider="openai",
            openai_api_key=req.api_key,
            openai_base_url=req.base_url,
            default_model=req.model or "gpt-4o-mini",
        )
    elif req.provider == "anthropic":
        update_runtime_llm_config(
            provider="anthropic",
            anthropic_api_key=req.api_key,
            anthropic_base_url=req.base_url,
            default_model=req.model or "claude-haiku-4-5-20251001",
        )
    elif req.provider == "openai_compatible":
        update_runtime_llm_config(
            provider="openai_compatible",
            openai_api_key=req.api_key,
            openai_base_url=req.base_url,
            default_model=req.model,
        )

    save_llm_config_to_disk()
    logger.info("llm_config_updated", provider=req.provider, base_url=req.base_url or "(default)")
    return await get_llm_settings()


# ---------------------------------------------------------------------------
# Voice settings — ASR (speech-to-text) and TTS (text-to-speech)
# ---------------------------------------------------------------------------


class VoiceConfigRequest(BaseModel):
    asr_api_key: str = ""
    asr_base_url: str = ""
    asr_model: str = ""
    tts_provider: str = ""        # openai | siliconflow | fish_audio | chattts
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_model: str = ""
    tts_voice_id: str = ""


class VoiceConfigResponse(BaseModel):
    asr_api_key_set: bool
    asr_base_url: str
    asr_model: str
    tts_provider: str
    tts_api_key_set: bool
    tts_base_url: str
    tts_model: str
    tts_voice_id: str


def _reload_voice_clients() -> None:
    """Re-create ASR/TTS clients so the new runtime config takes effect."""
    try:
        import voice_layer.api as api_mod
        from voice_layer.asr import ASRClient
        from voice_layer.tts import TTSClient

        api_mod.asr_client = ASRClient()
        api_mod.tts_client = TTSClient()
        logger.info("voice_clients_reloaded")
    except Exception as exc:
        logger.warning("voice_clients_reload_failed", error=str(exc))


@router.get(
    "/settings/voice",
    response_model=VoiceConfigResponse,
    tags=["settings"],
    summary="Get current voice (ASR/TTS) config",
)
async def get_voice_settings() -> VoiceConfigResponse:
    rt = get_runtime_voice_config()
    return VoiceConfigResponse(
        asr_api_key_set=bool(rt.get("asr_api_key")),
        asr_base_url=rt.get("asr_base_url") or "",
        asr_model=rt.get("asr_model") or "",
        tts_provider=rt.get("tts_provider") or "",
        tts_api_key_set=bool(rt.get("tts_api_key")),
        tts_base_url=rt.get("tts_base_url") or "",
        tts_model=rt.get("tts_model") or "",
        tts_voice_id=rt.get("tts_voice_id") or "",
    )


@router.post(
    "/settings/voice",
    response_model=VoiceConfigResponse,
    tags=["settings"],
    summary="Update voice (ASR/TTS) config at runtime",
)
async def save_voice_settings(req: VoiceConfigRequest) -> VoiceConfigResponse:
    update_runtime_voice_config(
        asr_api_key=req.asr_api_key,
        asr_base_url=req.asr_base_url,
        asr_model=req.asr_model,
        tts_provider=req.tts_provider,
        tts_api_key=req.tts_api_key,
        tts_base_url=req.tts_base_url,
        tts_model=req.tts_model,
        tts_voice_id=req.tts_voice_id,
    )
    save_voice_config_to_disk()
    _reload_voice_clients()
    logger.info("voice_config_updated", asr_base_url=req.asr_base_url or "(default)", tts_provider=req.tts_provider or "(default)")
    return await get_voice_settings()


# ---------------------------------------------------------------------------
# Project development status
# ---------------------------------------------------------------------------


@router.get(
    "/project_status",
    response_model=ProjectStatusData,
    tags=["development"],
    summary="Get project development status",
)
async def project_status() -> ProjectStatusData:
    """Return current development status of all modules."""
    return get_project_status()
