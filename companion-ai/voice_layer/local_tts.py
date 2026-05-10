"""Local TTS via piper-tts (ONNX neural voice).

Streams 16-bit PCM mono audio chunks for low-latency playback. The voice
model is loaded once at module init.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import structlog

logger = structlog.get_logger("voice_layer.local_tts")

_MODEL_DIR = Path(__file__).parent / "piper_models"
_DEFAULT_MODEL = os.getenv("COMPANION_PIPER_MODEL", "zh_CN-huayan-medium.onnx")

_voice: object | None = None
_voice_lock = threading.Lock()
_sample_rate: int = 22050


def _get_voice() -> object:
    global _voice, _sample_rate
    if _voice is not None:
        return _voice
    with _voice_lock:
        if _voice is not None:
            return _voice
        from piper import PiperVoice  # heavy import

        model_path = _MODEL_DIR / _DEFAULT_MODEL
        if not model_path.exists():
            raise FileNotFoundError(
                f"Piper voice model not found at {model_path}. "
                f"Download from https://hf-mirror.com/rhasspy/piper-voices"
            )
        logger.info("local_tts.loading", path=str(model_path))
        _voice = PiperVoice.load(str(model_path))
        try:
            _sample_rate = int(_voice.config.sample_rate)
        except Exception:
            _sample_rate = 22050
        logger.info("local_tts.loaded", sample_rate=_sample_rate)
        return _voice


def get_sample_rate() -> int:
    _get_voice()
    return _sample_rate


def synthesize_pcm_chunks_sync(text: str) -> Iterator[bytes]:
    """Synthesize text and yield raw 16-bit PCM mono chunks."""
    if not text or not text.strip():
        return
    voice = _get_voice()
    try:
        for chunk in voice.synthesize(text):
            audio_bytes = getattr(chunk, "audio_int16_bytes", None)
            if audio_bytes:
                yield audio_bytes
    except Exception as exc:
        logger.warning("local_tts.synthesize_failed", error=str(exc))


async def synthesize_pcm_chunks(text: str) -> AsyncIterator[bytes]:
    """Async generator wrapper. Runs synthesis in a worker thread, batches frames."""
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)
    loop = asyncio.get_running_loop()

    def _producer() -> None:
        try:
            for chunk in synthesize_pcm_chunks_sync(text):
                asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    threading.Thread(target=_producer, daemon=True).start()

    while True:
        item = await queue.get()
        if item is None:
            return
        yield item


def warmup() -> None:
    try:
        _get_voice()
    except Exception as exc:
        logger.warning("local_tts.warmup_failed", error=str(exc))
