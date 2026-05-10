"""FastAPI routers for voice_layer.

- POST /voice/transcribe — Accept audio blob, return VoiceTranscriptionResult
- POST /voice/synthesize — Accept VoiceSynthesisRequest, return audio URL + duration
- POST /voice/stream — WebSocket endpoint for real-time voice streaming
"""

import contextlib
import time
from urllib.parse import urlparse

import httpx
import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from starlette import status

from shared_contracts.models import VoiceSynthesisRequest, VoiceTranscriptionResult
from shared_runtime.voice_runtime_config import get_runtime_voice_config
from voice_layer.asr import ASRClient
from voice_layer.providers.realtime import get_realtime_status, init_registry, is_registry_initialized
from voice_layer.realtime import realtime_handler
from voice_layer.resolver import UnknownProviderError
from voice_layer.tts import TTSClient
from voice_layer.voice_errors import VoiceConfigurationError

logger = structlog.get_logger("voice_layer.api")

router = APIRouter(prefix="/voice", tags=["voice"])

# Shared clients (lifespan-managed in main.py)
asr_client: ASRClient | None = None
tts_client: TTSClient | None = None


def _get_asr() -> ASRClient:
    if asr_client is None:
        raise RuntimeError("ASR client not initialized")
    return asr_client


def _get_tts() -> TTSClient:
    if tts_client is None:
        raise RuntimeError("TTS client not initialized")
    return tts_client


def _err_body(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


@router.post("/transcribe", response_model=VoiceTranscriptionResult)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Audio blob to transcribe"),
    language: str = Form(default="zh-CN"),
) -> VoiceTranscriptionResult:
    """Transcribe an uploaded audio file to text with emotion detection."""
    audio_data = await audio.read()
    ct = audio.content_type
    fn = audio.filename
    logger.info(
        "api.transcribe.received",
        filename=fn,
        content_type=ct,
        size=len(audio_data),
        language=language,
    )
    try:
        return await _get_asr().transcribe(
            audio_data,
            language=language,
            upload_filename=fn,
            upload_content_type=ct,
        )
    except VoiceConfigurationError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=_err_body(exc.code, str(exc)),
        ) from exc
    except httpx.HTTPStatusError as exc:
        body = ""
        with contextlib.suppress(Exception):
            body = exc.response.text[:1200]
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=_err_body(
                "asr_upstream_error",
                f"ASR 上游错误 HTTP {exc.response.status_code}: {body or exc.response.reason_phrase}",
            ),
        ) from exc


@router.post("/synthesize")
async def synthesize_voice(request: VoiceSynthesisRequest) -> dict:
    """Synthesize speech from text and return audio URL + duration."""
    t0 = time.perf_counter()
    rt = get_runtime_voice_config()
    provider = (rt.get("tts_provider") or "").strip()
    model = (rt.get("tts_model") or "").strip()
    tts_voice = (rt.get("tts_voice_id") or "").strip()
    host = urlparse((rt.get("tts_base_url") or "").strip()).netloc or "unknown"
    logger.info(
        "api.synthesize.received",
        text_len=len(request.text),
        emotion=request.emotion.value,
        provider=provider,
        model=model,
        base_url_host=host,
        voice_id=tts_voice[:120] if tts_voice else "",
    )
    try:
        result = await _get_tts().synthesize(request)
    except VoiceConfigurationError as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning(
            "api.synthesize.config_error",
            provider=provider,
            model=model,
            base_url_host=host,
            latency_ms=latency_ms,
            code=exc.code,
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=_err_body(exc.code, str(exc)),
        ) from exc
    except UnknownProviderError as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning(
            "api.synthesize.voice_resolve_error",
            provider=provider,
            model=model,
            base_url_host=host,
            latency_ms=latency_ms,
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=_err_body("tts_voice_resolve", str(exc)),
        ) from exc
    except httpx.HTTPStatusError as exc:
        body = ""
        with contextlib.suppress(Exception):
            body = exc.response.text[:1200]
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning(
            "api.synthesize.upstream_http_error",
            provider=provider,
            model=model,
            base_url_host=host,
            voice_id=tts_voice[:120] if tts_voice else "",
            status=exc.response.status_code,
            latency_ms=latency_ms,
            body_preview=body[:300],
        )
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=_err_body(
                "tts_upstream_error",
                f"TTS 上游错误 HTTP {exc.response.status_code}: {body or exc.response.reason_phrase}",
            ),
        ) from exc
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.exception(
            "api.synthesize.unexpected_error",
            provider=provider,
            model=model,
            base_url_host=host,
            voice_id=tts_voice[:120] if tts_voice else "",
            latency_ms=latency_ms,
            err_type=type(exc).__name__,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_err_body("tts_internal_error", str(exc)),
        ) from exc

    latency_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "api.synthesize.ok",
        provider=provider,
        model=model,
        base_url_host=host,
        latency_ms=latency_ms,
        duration_ms=result.get("duration_ms"),
    )
    return {
        "audio_url": result["audio_url"],
        "voice_url": result["audio_url"],
        "duration_ms": result["duration_ms"],
        "local_path": result["local_path"],
    }


@router.get("/realtime/status")
async def realtime_status() -> dict:
    """Return current realtime voice provider status."""
    if not is_registry_initialized():
        init_registry()
    return get_realtime_status()


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket) -> None:
    """WebSocket for real-time voice streaming.

    Protocol:
        Client → Server: binary audio chunks (with optional JSON metadata prefix)
        Server → Client: JSON {type: "partial"|"final", text: ..., emotion: ..., confidence: ...}

    For MVP, buffers chunks and runs transcription on accumulated audio.
    """
    await websocket.accept()
    logger.info("api.stream.connected")

    buffer = bytearray()
    chunk_count = 0

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message:
                data = message["bytes"]
                buffer.extend(data)
                chunk_count += 1

                if len(buffer) > 80_000:
                    partial = await _try_partial_transcribe(bytes(buffer))
                    if partial:
                        await websocket.send_json({
                            "type": "partial",
                            "text": partial.text,
                            "emotion": partial.detected_emotion.value,
                            "confidence": partial.confidence,
                        })
                    overlap = int(len(buffer) * 0.2)
                    buffer = buffer[-overlap:]

            elif "text" in message:
                control = message["text"]
                logger.info("api.stream.control", control=control)
                if control == "finalize":
                    final = await _get_asr().transcribe(bytes(buffer))
                    await websocket.send_json({
                        "type": "final",
                        "text": final.text,
                        "emotion": final.detected_emotion.value,
                        "confidence": final.confidence,
                        "duration_ms": final.duration_ms,
                    })
                    buffer.clear()
                    chunk_count = 0
                elif control == "ping":
                    await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("api.stream.disconnected")
    except Exception as exc:
        logger.error("api.stream.error", error=str(exc))
        await websocket.close(code=1011)


@router.websocket("/realtime")
async def voice_realtime(websocket: WebSocket) -> None:
    """Real-time voice call pipeline (PCM in, transcript + TTS PCM out)."""
    await realtime_handler(websocket)


async def _try_partial_transcribe(audio_data: bytes) -> VoiceTranscriptionResult | None:
    """Attempt partial transcription; return None on failure."""
    try:
        return await _get_asr().transcribe(audio_data)
    except Exception as exc:
        logger.warning("api.stream.partial_failed", error=str(exc))
        return None
