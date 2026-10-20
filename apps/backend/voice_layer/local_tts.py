"""Local TTS via piper-tts (ONNX neural voice).

Streams 16-bit PCM mono audio chunks for low-latency playback. The voice
model is loaded once at module init.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import queue
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import structlog

logger = structlog.get_logger("voice_layer.local_tts")

_MODEL_DIR = Path(__file__).parent / "piper_models"
_DEFAULT_MODEL = os.getenv("COMPANION_PIPER_MODEL", "zh_CN-huayan-medium.onnx")

_voice: object | None = None
_voice_lock = threading.Lock()
_synthesis_lock = threading.Lock()
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
                f"Piper voice model not found at {model_path}. Download from https://hf-mirror.com/rhasspy/piper-voices"
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
    """Bounded thread bridge; no event-loop callbacks survive cancellation.

    Native inference may finish its current batch after interruption. Its output
    is discarded, and the engine lock is released before another synthesis.
    """
    frames: queue.Queue = queue.Queue(maxsize=8)
    stopped = threading.Event()

    def put(item):
        while not stopped.is_set():
            try:
                frames.put(item, timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def produce():
        acquired = False
        try:
            while not stopped.is_set():
                acquired = _synthesis_lock.acquire(timeout=0.05)
                if acquired:
                    break
            if not acquired or stopped.is_set():
                return
            with contextlib.closing(synthesize_pcm_chunks_sync(text)) as source:
                for chunk in source:
                    if not put(chunk):
                        break
        except Exception:
            put(RuntimeError("本地语音合成失败。"))
        finally:
            if acquired:
                _synthesis_lock.release()
            put(None)

    worker = threading.Thread(target=produce, daemon=True, name="companion-local-tts")
    worker.start()
    try:
        while True:
            try:
                item = await asyncio.to_thread(frames.get, True, 0.1)
            except queue.Empty:
                continue
            if item is None:
                return
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        stopped.set()
        # A native inference call cannot be force-cancelled; never hold the
        # interruption acknowledgement indefinitely waiting for it to return.
        await asyncio.to_thread(worker.join, 0.25)


def warmup() -> None:
    try:
        _get_voice()
    except Exception as exc:
        logger.warning("local_tts.warmup_failed", error=str(exc))
