"""Local ASR via faster-whisper.

Loads the model lazily on first use and reuses it across requests. Designed
for short utterances (1-15s) captured from the realtime WS pipeline.
"""

from __future__ import annotations

import asyncio
import os
import threading

import numpy as np
import structlog

logger = structlog.get_logger("voice_layer.local_asr")

_DEFAULT_MODEL_SIZE = os.getenv("COMPANION_WHISPER_MODEL", "base")
_DEFAULT_LANGUAGE = os.getenv("COMPANION_WHISPER_LANGUAGE", "zh")

# Use the HF mirror by default for users in mainland China unless overridden.
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

_model: object | None = None
_model_lock = threading.Lock()


def _get_model() -> object:
    """Singleton WhisperModel; built on first call."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel  # heavy import
        except ImportError as exc:
            raise ImportError(
                "缺少 faster-whisper。本地实时语音 ASR 需要安装："
                "pip install faster-whisper  或  pip install -e \".[voice-local]\""
            ) from exc

        logger.info("local_asr.loading", size=_DEFAULT_MODEL_SIZE)
        _model = WhisperModel(_DEFAULT_MODEL_SIZE, device="cpu", compute_type="int8")
        logger.info("local_asr.loaded")
        return _model


def transcribe_pcm_sync(pcm_int16: bytes, sample_rate: int = 16000) -> str:
    """Transcribe raw 16-bit PCM mono audio. Returns text."""
    if not pcm_int16:
        return ""
    audio = np.frombuffer(pcm_int16, dtype=np.int16).astype(np.float32) / 32768.0
    if sample_rate != 16000:
        # naive resample via numpy (not high quality but fine for ASR)
        ratio = 16000 / sample_rate
        new_len = int(len(audio) * ratio)
        idx = np.linspace(0, len(audio) - 1, new_len).astype(np.int64)
        audio = audio[idx]
    model = _get_model()
    segments, _info = model.transcribe(
        audio,
        language=_DEFAULT_LANGUAGE,
        beam_size=1,
        vad_filter=False,
        condition_on_previous_text=False,
    )
    return "".join(seg.text for seg in segments).strip()


async def transcribe_pcm(pcm_int16: bytes, sample_rate: int = 16000) -> str:
    """Async wrapper running transcription in a worker thread."""
    return await asyncio.to_thread(transcribe_pcm_sync, pcm_int16, sample_rate)


def warmup() -> None:
    """Trigger model load eagerly. Safe to call from startup hook."""
    try:
        _get_model()
    except Exception as exc:
        logger.warning("local_asr.warmup_failed", error=str(exc))
