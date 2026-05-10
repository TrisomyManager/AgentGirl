"""DashScope (Aliyun) Paraformer real-time ASR provider.

Encapsulates the ``dashscope`` SDK so that ``voice_layer/asr.py`` does not
directly import ``dashscope``, satisfying ADR-006 hard constraint 2.

The provider implements the ``ASRProvider`` Protocol from ``shared_contracts``
for hosts that use injection, and exposes a standalone ``transcribe_dashscope``
helper for the monolithic ``ASRClient`` path.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger("voice_layer.providers.dashscope")


async def transcribe_dashscope(
    audio_data: bytes,
    *,
    api_key: str,
    model: str = "paraformer-realtime-v2",
    sample_rate: int = 16000,
) -> tuple[str, float]:
    """Transcribe audio via DashScope Paraformer streaming ASR.

    Args:
        audio_data: WAV 16kHz mono PCM bytes.
        api_key: DashScope API key.
        model: Model name (default ``paraformer-realtime-v2``).
        sample_rate: Audio sample rate in Hz.

    Returns:
        (transcript_text, confidence) tuple.
    """

    def _run() -> str:
        import dashscope
        from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

        dashscope.api_key = api_key
        collected: list[str] = []

        class _CB(RecognitionCallback):
            def on_open(self) -> None:
                pass

            def on_close(self) -> None:
                pass

            def on_complete(self) -> None:
                pass

            def on_error(self, msg: Any) -> None:
                logger.warning("dashscope.asr.error", msg=str(msg))

            def on_event(self, result: RecognitionResult) -> None:
                sentence = result.get_sentence()
                if not sentence or "text" not in sentence:
                    return
                if RecognitionResult.is_sentence_end(sentence):
                    collected.append(sentence["text"])

        cb = _CB()
        rec = Recognition(
            model=model,
            format="wav",
            sample_rate=sample_rate,
            callback=cb,
            language_hints=["zh", "en"],
        )
        rec.start()
        chunk = 3200
        try:
            for i in range(0, len(audio_data), chunk):
                rec.send_audio_frame(audio_data[i : i + chunk])
        finally:
            rec.stop()
        return "".join(collected)

    text = await asyncio.to_thread(_run)
    return text, 0.9


class DashScopeASRProvider:
    """DashScope ASR provider implementing ``ASRProvider`` Protocol shape.

    Hosts can instantiate and inject this into ``voice_layer`` where an
    ``ASRProvider`` Protocol is expected.
    """

    def __init__(self, api_key: str, model: str = "paraformer-realtime-v2") -> None:
        self._api_key = api_key
        self._model = model

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        sample_rate: int = 16000,
        **kwargs: Any,
    ) -> str:
        text, _confidence = await transcribe_dashscope(
            audio_bytes,
            api_key=self._api_key,
            model=self._model,
            sample_rate=sample_rate,
        )
        return text
