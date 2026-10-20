"""FastAPI routers for core_orchestrator.

Endpoints:
  POST /orchestrator/turn    — Main entry point for processing a user turn
  POST /orchestrator/health  — Health check (module-level)
  GET  /orchestrator/status  — Show connected modules status
"""

from __future__ import annotations

import json
import uuid
from contextlib import aclosing
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core_orchestrator.orchestrator import get_orchestrator
from core_orchestrator.project_status import ProjectStatusData, get_project_status
from shared_contracts.models import (
    DeviceInfo,
    Platform,
    TurnContext,
    UserProfile,
)
from shared_contracts.avatar import AvatarTimeline
from shared_runtime.config import get_settings
from shared_runtime.llm_client import get_runtime_llm_config, save_llm_config_to_disk, update_runtime_llm_config
from shared_runtime.voice_runtime_config import (
    clear_runtime_voice_config,
    get_effective_voice_config,
    save_voice_config_to_disk,
    update_runtime_voice_config,
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
    request_voice_reply: bool = False
    supports_segmented_voice: bool = False
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
    expression_emoji: Optional[str] = None
    reply_suppressed: bool = False
    content_filtered: bool = False
    talk_value: float = 1.0
    reply_reason: Optional[str] = None
    voice_url: Optional[str] = None
    voice_duration_ms: Optional[int] = None
    voice_error: Optional[str] = None
    voice_mode: Optional[str] = None
    voice_segments: List[Dict[str, Any]] = []
    avatar_timeline: AvatarTimeline | None = None
    action_sequence: Optional[Dict[str, Any]] = None
    intent: Optional[str] = None
    intent_confidence: Optional[float] = None
    memory_entries_count: int = 0
    error: Optional[str] = None
    specialist: str = "chat"
    task: Optional[Dict[str, Any]] = None


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
    response_model_exclude_none=False,
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
        request_voice_reply=request.request_voice_reply,
        supports_segmented_voice=request.supports_segmented_voice,
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
    "/turn/stream",
    summary="Process a user turn and stream tokens as SSE",
    response_class=StreamingResponse,
)
async def process_turn_stream(request: TurnRequest) -> StreamingResponse:
    """SSE variant of ``/orchestrator/turn``.

    Emits one of the following events per SSE frame:
      ``meta``  — once after intent classification + memory recall.
      ``token`` — one per LLM chunk; concatenate ``data.text`` to rebuild the
                  full assistant message.
      ``done``  — final TurnResponse-shaped payload (assistant_message,
                  emotion, voice_url, action_sequence, intent, ...).
      ``error`` — provider/network/state-machine error (non-fatal events
                  still emit ``done`` afterwards).

    Encoding follows the standard SSE wire format::

        event: token
        data: {"text": "你"}

        event: token
        data: {"text": "好"}

        event: done
        data: {"assistant_message": "你好", ...}
    """
    turn_id = str(uuid.uuid4())
    log = logger.bind(turn_id=turn_id, session_id=request.session_id)
    log.info(
        "api_turn_stream_request",
        user_id=request.user.user_id,
        platform=request.platform.value,
    )

    turn_context = TurnContext(
        turn_id=turn_id,
        session_id=request.session_id,
        user=request.user,
        user_message=request.user_message,
        platform=request.platform,
        has_voice=request.has_voice,
        request_voice_reply=request.request_voice_reply,
        supports_segmented_voice=request.supports_segmented_voice,
        voice_duration_ms=request.voice_duration_ms,
        has_image=request.has_image,
        image_urls=request.image_urls,
        device_info=request.device_info,
    )

    async def _sse_generator() -> AsyncIterator[bytes]:
        try:
            orch = await get_orchestrator()
        except Exception as exc:
            log.exception("api_turn_stream_orchestrator_error", error=str(exc))
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n".encode("utf-8")
            yield b"event: done\ndata: {}\n\n"
            return

        try:
            async with aclosing(orch.process_turn_stream(turn_context)) as stream:
                async for event in stream:
                    event_name = event.pop("event", "message")
                    payload = json.dumps(event, ensure_ascii=False, default=str)
                    yield f"event: {event_name}\ndata: {payload}\n\n".encode("utf-8")
        except Exception as exc:
            log.exception("api_turn_stream_error", error=str(exc))
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n".encode("utf-8")
            yield b"event: done\ndata: {}\n\n"

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Tell reverse proxies / Cloudflare not to buffer
            "X-Accel-Buffering": "no",
        },
    )


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
    provider: str = ""          # volcengine | openai | anthropic | openai_compatible
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
    from shared_runtime.llm_client import LLMClient

    rt = get_runtime_llm_config()
    client = LLMClient()
    provider = rt.get("provider") or (
        "anthropic" if client.anthropic_api_key and not client.openai_api_key else "volcengine"
    )
    return LlmConfigResponse(
        provider=provider,
        api_key_set=client.has_configured_provider(),
        base_url=client.anthropic_base_url if provider == "anthropic" else client.openai_base_url,
        model=client.default_model,
    )


@router.post(
    "/settings/llm",
    response_model=LlmConfigResponse,
    tags=["settings"],
    summary="Update LLM config at runtime",
)
async def save_llm_settings(req: LlmConfigRequest) -> LlmConfigResponse:
    """Persist LLM settings.

    Empty ``api_key`` in the request means "keep the previously saved key" so
    the UI can save model/base_url changes without forcing users to re-paste
    secrets (the settings form clears the key field after load).
    """
    from shared_runtime.model_presets import ARK_BASE_URL, CHAT_MODEL

    if req.provider not in {"", "volcengine", "openai", "openai_compatible", "anthropic"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不支持的模型服务商")
    rt_before = get_runtime_llm_config()
    settings = get_settings()
    selected = req.provider
    values = {"provider": selected, "openai_api_key": "", "anthropic_api_key": "",
              "openai_base_url": "", "anthropic_base_url": "", "default_model": ""}
    if selected:
        key_field = "anthropic_api_key" if selected == "anthropic" else "openai_api_key"
        same_provider = rt_before.get("provider") == selected
        # Never carry another vendor's secret into a newly selected provider.
        previous_key = rt_before.get(key_field, "") if same_provider else ""
        env_key = settings.ark_api_key if selected == "volcengine" else getattr(settings, key_field)
        api_key = req.api_key.strip() or previous_key or env_key or ""
        if not api_key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="请填写 API Key；同一服务商可保留已保存的 Key。")
        default_model = {"volcengine": CHAT_MODEL, "openai": "gpt-4o-mini",
                         "anthropic": "claude-haiku-4-5-20251001"}.get(selected, "")
        model = req.model.strip() or (rt_before.get("default_model", "") if same_provider else "") or default_model
        if not model:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="请填写模型 ID 或推理接入点 ID。")
        values.update({key_field: api_key, "default_model": model})
        values["anthropic_base_url" if selected == "anthropic" else "openai_base_url"] = (
            req.base_url.strip() or (ARK_BASE_URL if selected == "volcengine" else "")
        )
    update_runtime_llm_config(**values)

    save_llm_config_to_disk()
    logger.info("llm_config_updated", provider=req.provider, base_url=req.base_url or "(default)")
    return await get_llm_settings()


class LlmTestResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    base_url: str
    latency_ms: int
    sample_reply: str = ""
    error: str = ""


@router.post(
    "/settings/llm/test",
    response_model=LlmTestResponse,
    tags=["settings"],
    summary="Test the current LLM config with a tiny round-trip call",
)
async def test_llm_settings() -> LlmTestResponse:
    """Send a minimal prompt to the configured LLM and time the response.

    Uses the current runtime settings (whatever the user just saved) and does
    NOT require any request body. Returns latency + a sample reply on success,
    or a friendly error message on failure (network / 401 / wrong base_url /
    wrong model name etc.).
    """
    import time

    from shared_runtime.llm_client import LLMClient

    effective = await get_llm_settings()
    provider, model, base_url = effective.provider, effective.model, effective.base_url
    has_key = effective.api_key_set

    if not has_key or not provider:
        return LlmTestResponse(
            ok=False,
            provider=provider,
            model=model,
            base_url=base_url,
            latency_ms=0,
            error="未配置 LLM Provider 或 API Key，请先保存配置后再测试。",
        )

    client = LLMClient()
    started = time.perf_counter()
    try:
        reply = await client.generate(
            system_prompt="你是一个测试助手。请用一句话简短回复。",
            user_message="ping",
            temperature=0.0,
            max_tokens=32,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        sample = (reply.get("assistant_message") or "").strip()
        if len(sample) > 200:
            sample = sample[:200] + "..."
        return LlmTestResponse(
            ok=True,
            provider=provider,
            model=model,
            base_url=base_url,
            latency_ms=elapsed_ms,
            sample_reply=sample or "(空回复)",
        )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        msg = str(exc) or exc.__class__.__name__
        logger.warning("llm_test_failed", provider=provider, model=model, error=msg)
        return LlmTestResponse(
            ok=False,
            provider=provider,
            model=model,
            base_url=base_url,
            latency_ms=elapsed_ms,
            error=msg,
        )
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001
            pass


class VoiceTestResponse(BaseModel):
    asr_ok: bool
    asr_provider: str
    asr_model: str
    asr_message: str = ""
    tts_ok: bool
    tts_provider: str
    tts_model: str
    tts_voice: str
    tts_latency_ms: int
    tts_audio_url: str = ""
    tts_duration_ms: int = 0
    tts_error: str = ""


@router.post(
    "/settings/voice/test",
    response_model=VoiceTestResponse,
    tags=["settings"],
    summary="Test ASR/TTS configs without doing a real call",
)
async def test_voice_settings() -> VoiceTestResponse:
    """Verify ASR + TTS are usable.

    - ASR: checks config presence (we don't have an audio file to send here,
      so we just confirm key/base_url/model are set; full validation happens
      on first /voice/realtime use).
    - TTS: synthesizes a short Chinese sentence and returns the audio URL +
      latency. Failures show the upstream error so users can fix the config.
    """
    import time

    from shared_contracts.models import EmotionTag, VoiceSynthesisRequest

    rt = get_effective_voice_config()

    from voice_layer.asr import ASRClient

    asr_provider = ASRClient._infer_provider(rt.get("asr_base_url") or "")
    asr_ok = bool(rt.get("asr_api_key") and rt.get("asr_base_url") and rt.get("asr_model"))
    asr_msg = (
        "ASR 配置完整，将在下一次通话使用"
        if asr_ok
        else "ASR 未配置完整：需要 API Key + Base URL + 模型"
    )

    tts_provider = (rt.get("tts_provider") or "").strip()
    tts_model = (rt.get("tts_model") or "").strip()
    tts_voice = (rt.get("tts_voice_id") or "").strip()
    tts_has_key = bool(rt.get("tts_api_key"))

    tts_base_ok = bool((rt.get("tts_base_url") or "").strip())
    if not tts_provider or not tts_has_key or not tts_base_ok or not tts_model:
        return VoiceTestResponse(
            asr_ok=asr_ok,
            asr_provider=asr_provider,
            asr_model=rt.get("asr_model") or "",
            asr_message=asr_msg,
            tts_ok=False,
            tts_provider=tts_provider,
            tts_model=tts_model,
            tts_voice=tts_voice,
            tts_latency_ms=0,
            tts_error="TTS 需配置：提供商、API Key、Base URL 与模型（设置页保存后生效）",
        )

    try:
        from voice_layer.tts import TTSClient
        client = TTSClient()
    except Exception as exc:  # noqa: BLE001
        return VoiceTestResponse(
            asr_ok=asr_ok,
            asr_provider=asr_provider,
            asr_model=rt.get("asr_model") or "",
            asr_message=asr_msg,
            tts_ok=False,
            tts_provider=tts_provider,
            tts_model=tts_model,
            tts_voice=tts_voice,
            tts_latency_ms=0,
            tts_error=f"无法初始化 TTS 客户端: {exc}",
        )

    started = time.perf_counter()
    try:
        req = VoiceSynthesisRequest(
            text="语音合成测试，你好。",
            emotion=EmotionTag.NEUTRAL,
            voice_id=None,
            speed=1.0,
        )
        result = await client.synthesize(req)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return VoiceTestResponse(
            asr_ok=asr_ok,
            asr_provider=asr_provider,
            asr_model=rt.get("asr_model") or "",
            asr_message=asr_msg,
            tts_ok=True,
            tts_provider=tts_provider,
            tts_model=tts_model,
            tts_voice=tts_voice,
            tts_latency_ms=elapsed_ms,
            tts_audio_url=result.get("audio_url", ""),
            tts_duration_ms=int(result.get("duration_ms", 0)),
        )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        msg = str(exc) or exc.__class__.__name__
        logger.warning("voice_test_failed", provider=tts_provider, model=tts_model, error=msg)
        return VoiceTestResponse(
            asr_ok=asr_ok,
            asr_provider=asr_provider,
            asr_model=rt.get("asr_model") or "",
            asr_message=asr_msg,
            tts_ok=False,
            tts_provider=tts_provider,
            tts_model=tts_model,
            tts_voice=tts_voice,
            tts_latency_ms=elapsed_ms,
            tts_error=msg,
        )


# ---------------------------------------------------------------------------
# Voice settings — ASR (speech-to-text) and TTS (text-to-speech)
# ---------------------------------------------------------------------------


class VoiceConfigRequest(BaseModel):
    reset: bool = False
    asr_api_key: str = ""
    asr_base_url: str = ""
    asr_model: str = ""
    tts_provider: str = ""        # openai | siliconflow | fish_audio | chattts
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_model: str = ""
    tts_voice_id: str = ""
    realtime_voice_provider: str = "volc_realtime"
    volc_api_key: str = ""
    volc_model: str = "1.2.1.1"
    volc_voice_id: str = "zh_female_xiaohe_jupiter_bigtts"


class VoiceConfigResponse(BaseModel):
    asr_api_key_set: bool
    asr_base_url: str
    asr_model: str
    tts_provider: str
    tts_api_key_set: bool
    tts_base_url: str
    tts_model: str
    tts_voice_id: str
    realtime_voice_provider: str
    volc_api_key_set: bool
    volc_model: str
    volc_voice_id: str


def _reload_voice_clients() -> None:
    """Reload TTS; ASR is factory-owned per operation and never replaced here."""
    try:
        import voice_layer.api as api_mod
        from voice_layer.tts import TTSClient

        api_mod.tts_client = TTSClient()
        logger.info("voice_clients_reloaded")
    except Exception as exc:
        logger.warning("voice_clients_reload_failed", error=str(exc))


def _infer_effective_tts_provider(base_url: str, provider_hint: str = "") -> str:
    lowered = (base_url or "").lower()
    if "dashscope" in lowered:
        return "dashscope"
    if "siliconflow" in lowered:
        return "siliconflow"
    if provider_hint in {"openai", "openai_compatible"}:
        return "openai"
    return "openai"


@router.get(
    "/settings/voice",
    response_model=VoiceConfigResponse,
    tags=["settings"],
    summary="Get current voice (ASR/TTS) config",
)
async def get_voice_settings() -> VoiceConfigResponse:
    rt = get_effective_voice_config()
    return VoiceConfigResponse(
        asr_api_key_set=bool(rt.get("asr_api_key")),
        asr_base_url=rt.get("asr_base_url") or "",
        asr_model=rt.get("asr_model") or "",
        tts_provider=rt.get("tts_provider") or "",
        tts_api_key_set=bool(rt.get("tts_api_key")),
        tts_base_url=rt.get("tts_base_url") or "",
        tts_model=rt.get("tts_model") or "",
        tts_voice_id=rt.get("tts_voice_id") or "",
        realtime_voice_provider=rt.get("realtime_voice_provider") or "volc_realtime",
        volc_api_key_set=bool(rt.get("volc_api_key")),
        volc_model=rt.get("volc_model") or "",
        volc_voice_id=rt.get("volc_voice_id") or "",
    )


@router.post(
    "/settings/voice",
    response_model=VoiceConfigResponse,
    tags=["settings"],
    summary="Update voice (ASR/TTS) config at runtime",
)
async def save_voice_settings(req: VoiceConfigRequest) -> VoiceConfigResponse:
    # Preserve existing API keys when the request leaves them blank
    # (the UI clears the input fields after load so users don't have to
    # re-paste secrets just to change a model name or base url).
    if req.reset:
        clear_runtime_voice_config()
    else:
        if req.realtime_voice_provider not in {"local", "cloud", "volc_realtime"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不支持的实时语音服务商")
        from urllib.parse import urlparse

        rt_before = get_effective_voice_config()
        same_asr = urlparse(req.asr_base_url).netloc == urlparse(rt_before.get("asr_base_url") or "").netloc
        same_tts = (req.tts_provider == rt_before.get("tts_provider") and
                    urlparse(req.tts_base_url).netloc == urlparse(rt_before.get("tts_base_url") or "").netloc)
        asr_api_key = req.asr_api_key.strip() or (rt_before.get("asr_api_key", "") if same_asr else "")
        tts_api_key = req.tts_api_key.strip() or (rt_before.get("tts_api_key", "") if same_tts else "")
        update_runtime_voice_config(
            asr_api_key=asr_api_key,
            asr_base_url=req.asr_base_url,
            asr_model=req.asr_model,
            tts_provider=req.tts_provider,
            tts_api_key=tts_api_key,
            tts_base_url=req.tts_base_url,
            tts_model=req.tts_model,
            tts_voice_id=req.tts_voice_id,
            realtime_voice_provider=req.realtime_voice_provider,
            volc_api_key=req.volc_api_key.strip() or rt_before.get("volc_api_key", ""),
            volc_model=req.volc_model,
            volc_voice_id=req.volc_voice_id,
        )
    save_voice_config_to_disk()
    _reload_voice_clients()
    from voice_layer.providers.realtime import init_registry, reset_realtime_registry

    reset_realtime_registry()
    init_registry()
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


@router.post(
    "/debug/prompt_preview",
    tags=["development"],
    summary="Preview assembled conversation system prompt for a hypothetical turn",
)
async def debug_prompt_preview(request: TurnRequest) -> Dict[str, Any]:
    """Build the same system prompt as the reply path (``node_generate_response``) without calling the LLM."""
    from core_orchestrator.state_machine import build_prompt_preview

    turn_id = str(uuid.uuid4())
    tc = TurnContext(
        turn_id=turn_id,
        session_id=request.session_id,
        user=request.user,
        user_message=request.user_message,
        platform=request.platform,
        has_voice=request.has_voice,
        request_voice_reply=request.request_voice_reply,
        voice_duration_ms=request.voice_duration_ms,
        has_image=request.has_image,
        image_urls=request.image_urls,
        device_info=request.device_info,
    )
    system_prompt = await build_prompt_preview(tc)
    return {
        "turn_id": turn_id,
        "session_id": tc.session_id,
        "user_id": tc.user.user_id,
        "system_prompt": system_prompt,
        "prompt_length": len(system_prompt),
        "intent": request.user_message[:100],
    }


@router.get(
    "/debug/system_prompt",
    tags=["development"],
    summary="Last assembled conversation system prompt (debug)",
)
async def debug_system_prompt() -> Dict[str, Any]:
    """Return the most recent ``build_conversation_system_prompt`` output from a turn."""
    from core_orchestrator.state_machine import get_debug_system_prompt_snapshot

    return get_debug_system_prompt_snapshot()


# ---------------------------------------------------------------------------
# Onboarding endpoints — first-time user flow → role_id → user_profile
# ---------------------------------------------------------------------------


class OnboardingStartRequest(BaseModel):
    user_id: str


class OnboardingAnswerRequest(BaseModel):
    user_id: str
    answer: str


@router.post(
    "/onboarding/start",
    tags=["onboarding"],
    summary="Start or resume onboarding flow for a user",
)
async def onboarding_start(req: OnboardingStartRequest) -> Dict[str, Any]:
    """Begin onboarding: returns the first question prompt."""
    from onboarding import OnboardingFlow, default_steps

    flow = OnboardingFlow(user_id=req.user_id)
    _active_flows[req.user_id] = flow
    prompt = flow.current_prompt()
    return {
        "user_id": req.user_id,
        "step": flow.current_step().key if flow.current_step() else None,
        "prompt": prompt,
        "is_complete": flow.is_complete,
    }


@router.post(
    "/onboarding/answer",
    tags=["onboarding"],
    summary="Submit an answer during onboarding",
)
async def onboarding_answer(req: OnboardingAnswerRequest) -> Dict[str, Any]:
    """Submit an answer and get the next prompt (or completion)."""
    from onboarding import OnboardingFlow, apply_to_profile
    from user_profile import get_default_store

    flow = _active_flows.get(req.user_id)
    if flow is None:
        from onboarding import OnboardingFlow

        flow = OnboardingFlow(user_id=req.user_id)
        _active_flows[req.user_id] = flow

    next_step = flow.submit_answer(req.answer)
    if flow.is_complete:
        await apply_to_profile(flow.result, get_default_store())
        del _active_flows[req.user_id]
        return {
            "user_id": req.user_id,
            "is_complete": True,
            "result": {
                "role_id": flow.result.role_id,
                "nickname": flow.result.nickname,
                "locale": flow.result.locale,
                "completed_steps": flow.result.completed_steps,
            },
        }

    return {
        "user_id": req.user_id,
        "step": next_step.key if next_step else None,
        "prompt": next_step.prompt if next_step else None,
        "is_complete": False,
    }


@router.get(
    "/onboarding/status",
    tags=["onboarding"],
    summary="Check onboarding status for a user",
)
async def onboarding_status(user_id: str) -> Dict[str, Any]:
    """Check if onboarding is complete and what profile was set."""
    from user_profile import get_default_store

    profile = await get_default_store().get(user_id)
    if profile and profile.preferences.get("role_id"):
        return {
            "user_id": user_id,
            "onboarded": True,
            "role_id": profile.preferences.get("role_id"),
            "nickname": profile.display_name,
            "locale": profile.locale,
        }
    return {"user_id": user_id, "onboarded": False}


_active_flows: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Debug state endpoint — full personality state visibility for diagnostics
# ---------------------------------------------------------------------------


@router.get(
    "/debug/state",
    tags=["development"],
    summary="Full personality state snapshot (emotion / relationship / memory / intent)",
)
async def debug_state(session_id: str, user_id: str = "") -> Dict[str, Any]:
    """Return a comprehensive debug snapshot of the conversation state engine.

    Includes:
    - Last system prompt
    - Current emotion_state
    - Relationship metrics
    - Working memory for the session
    - Recalled long-term memories (last snapshot)
    - Intent classification (last snapshot)
    """
    from core_orchestrator.state_machine import get_debug_system_prompt_snapshot

    result: Dict[str, Any] = {
        "session_id": session_id,
        "user_id": user_id,
        "system_prompt": None,
        "emotion_state": None,
        "relationship_metrics": None,
        "working_memory": None,
        "recalled_memories": None,
        "intent": None,
    }

    # System prompt snapshot
    snap = get_debug_system_prompt_snapshot()
    if snap.get("system_prompt"):
        result["system_prompt"] = snap["system_prompt"]

    # Emotion state from emotion_engine
    if user_id:
        try:
            from persona_engine.runtime import get_emotion_engine
            engine = get_emotion_engine()
            emotion = await engine.get_current_emotion(user_id)
            result["emotion_state"] = emotion.model_dump(mode="json")
        except Exception:
            pass

        # Relationship metrics
        try:
            from persona_engine.runtime import get_relationship_tracker
            tracker = get_relationship_tracker()
            rel = await tracker.get_metrics(user_id)
            result["relationship_metrics"] = rel.model_dump(mode="json")
        except Exception:
            pass

        # User profile
        try:
            from user_profile import get_default_store
            profile = await get_default_store().get(user_id)
            if profile:
                result["user_profile"] = {
                    "display_name": profile.display_name,
                    "locale": profile.locale,
                    "preferences": profile.preferences,
                    "traits": profile.traits,
                }
        except Exception:
            pass

    # Working memory
    if session_id:
        try:
            from memory_system.working import get_working_memory
            wm = get_working_memory()
            window = await wm.get_window(session_id)
            if window:
                result["working_memory"] = {
                    "turn_count": len(window),
                    "recent_turns": [
                        {
                            "user": t.get("user", "")[:200],
                            "assistant": t.get("assistant", "")[:200],
                            "emotion": t.get("emotion"),
                            "intent": t.get("intent"),
                        }
                        for t in window[-5:]
                    ],
                }
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Persona listing — available roles for onboarding
# ---------------------------------------------------------------------------


@router.get(
    "/personas",
    tags=["persona"],
    summary="List available persona roles",
)
async def list_personas() -> Dict[str, Any]:
    """Return all available persona role_ids and their display names."""
    try:
        from persona_engine.persona_store import get_persona_profile, list_available_personas

        role_ids = list_available_personas()
        personas = []
        for rid in role_ids:
            try:
                profile = get_persona_profile(role_id=rid)
                personas.append({
                    "role_id": rid,
                    "name": profile.name,
                    "core_traits": profile.core_traits[:3] if profile.core_traits else [],
                    "communication_style": (profile.communication_style or "")[:80],
                })
            except Exception:
                personas.append({"role_id": rid, "name": rid})
        return {"personas": personas}
    except Exception:
        return {"personas": [{"role_id": "default", "name": "小暖"}]}
