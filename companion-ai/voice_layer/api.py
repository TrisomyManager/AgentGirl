"""FastAPI routers for voice_layer.

- POST /voice/transcribe — Accept audio blob, return VoiceTranscriptionResult
- POST /voice/synthesize — Accept VoiceSynthesisRequest, return audio URL + duration
- POST /voice/stream — WebSocket endpoint for real-time voice streaming
"""

from fastapi import APIRouter, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

import structlog

from shared.models import VoiceSynthesisRequest, VoiceTranscriptionResult
from voice_layer.asr import ASRClient
from voice_layer.realtime import realtime_handler
from voice_layer.tts import TTSClient

logger = structlog.get_logger("voice_layer.api")

router = APIRouter(prefix="/voice", tags=["voice"])

# Shared clients (lifespan-managed in main.py)
asr_client: ASRClient | None = None
tts_client: TTSClient | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_asr() -> ASRClient:
    if asr_client is None:
        raise RuntimeError("ASR client not initialized")
    return asr_client


def _get_tts() -> TTSClient:
    if tts_client is None:
        raise RuntimeError("TTS client not initialized")
    return tts_client


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@router.post("/transcribe", response_model=VoiceTranscriptionResult)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Audio blob to transcribe"),
    language: str = Form(default="zh-CN"),
) -> VoiceTranscriptionResult:
    """Transcribe an uploaded audio file to text with emotion detection."""
    audio_data = await audio.read()
    logger.info("api.transcribe.received", filename=audio.filename, size=len(audio_data), language=language)

    result = await _get_asr().transcribe(audio_data, language=language)
    return result


@router.post("/synthesize")
async def synthesize_voice(request: VoiceSynthesisRequest) -> dict:
    """Synthesize speech from text and return audio URL + duration."""
    logger.info("api.synthesize.received", text_len=len(request.text), emotion=request.emotion.value)

    result = await _get_tts().synthesize(request)
    return {
        "audio_url": result["audio_url"],
        "duration_ms": result["duration_ms"],
        "local_path": result["local_path"],
    }


# ---------------------------------------------------------------------------
# WebSocket streaming
# ---------------------------------------------------------------------------

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

                # Every ~5 seconds of audio (roughly 80KB @ 128kbps), emit partial
                if len(buffer) > 80_000:
                    partial = await _try_partial_transcribe(bytes(buffer))
                    if partial:
                        await websocket.send_json({
                            "type": "partial",
                            "text": partial.text,
                            "emotion": partial.detected_emotion.value,
                            "confidence": partial.confidence,
                        })
                    # Keep last 20% as overlap for next window
                    overlap = int(len(buffer) * 0.2)
                    buffer = buffer[-overlap:]

            elif "text" in message:
                # Control message from client
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
