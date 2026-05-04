"""ASR client wrapper — Whisper API / Groq / SiliconFlow / DashScope (Paraformer).

Supports transcription and emotion detection from prosody via LLM.
"""

import asyncio
import base64
import io
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shared.config import get_settings
from shared.models import EmotionTag, VoiceTranscriptionResult
from shared.voice_runtime_config import get_runtime_voice_config

logger = structlog.get_logger("voice_layer.asr")

# ---------------------------------------------------------------------------
# Emotion detection prompt
# ---------------------------------------------------------------------------

_EMOTION_PROMPT = """You are an emotion classifier. Given a transcript and optional context, classify the speaker's primary emotion.

Available emotions: neutral, happy, sad, angry, surprised, fearful, disgusted, affectionate, concerned, excited, calm

Transcript: {transcript}
Language: {language}

Respond with ONLY the emotion label (lowercase)."""


# ---------------------------------------------------------------------------
# ASR Client
# ---------------------------------------------------------------------------

class ASRClient:
    """Async ASR client supporting Whisper API, Groq, and OpenAI."""

    def __init__(self) -> None:
        settings = get_settings()
        rt = get_runtime_voice_config()  # frontend-managed overrides win
        self.provider = "openai"  # default; inferred from base_url below
        self.api_key = (
            rt.get("asr_api_key")
            or settings.whisper_api_key
            or settings.openai_api_key
        )
        self.base_url = (
            rt.get("asr_base_url")
            or settings.whisper_base_url
            or settings.openai_base_url
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.default_model = rt.get("asr_model") or "whisper-1"
        self.timeout = 60.0

        # Infer provider from base_url
        if "dashscope" in self.base_url.lower() or "aliyuncs" in self.base_url.lower():
            self.provider = "dashscope"
            if not rt.get("asr_model"):
                self.default_model = "paraformer-realtime-v2"
        elif "groq" in self.base_url.lower():
            self.provider = "groq"
            if not rt.get("asr_model"):
                self.default_model = "whisper-large-v3"
        elif "siliconflow" in self.base_url.lower():
            self.provider = "siliconflow"
            if not rt.get("asr_model"):
                self.default_model = "FunAudioLLM/SenseVoiceSmall"
        elif "openai" in self.base_url.lower():
            self.provider = "openai"
            if not rt.get("asr_model"):
                self.default_model = "whisper-1"
        else:
            self.provider = "custom"

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "zh-CN",
        model: str | None = None,
    ) -> VoiceTranscriptionResult:
        """Transcribe audio bytes to text.

        Returns a VoiceTranscriptionResult with text, confidence, and detected emotion.
        """
        model = model or self.default_model
        logger.info("asr.transcribe.start", provider=self.provider, model=model, language=language)

        if self.provider == "dashscope":
            text, confidence = await self._transcribe_dashscope(audio_data, model)
        else:
            text, confidence = await self._transcribe_openai_compat(audio_data, model, language)

        logger.info("asr.transcribe.end", provider=self.provider, text_len=len(text), confidence=confidence)

        # Detect emotion from transcript context
        detected_emotion = await self._detect_emotion(text, language)

        # Estimate duration from audio size (rough fallback)
        duration_ms = len(audio_data) // 32  # ~32 bytes/ms for 256kbps mp3 rough estimate

        return VoiceTranscriptionResult(
            text=text,
            confidence=confidence,
            detected_emotion=detected_emotion,
            language=language,
            duration_ms=duration_ms,
        )

    async def _transcribe_openai_compat(
        self, audio_data: bytes, model: str, language: str
    ) -> tuple[str, float]:
        """OpenAI-compatible /audio/transcriptions endpoint (Whisper / Groq / SiliconFlow)."""
        client = await self._get_client()
        whisper_lang = language.split("-")[0] if language.startswith("zh") else language
        files = {
            "file": ("audio.webm", io.BytesIO(audio_data), "audio/webm"),
        }
        data = {
            "model": model,
            "language": whisper_lang,
            "response_format": "json",
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/audio/transcriptions"
        response = await client.post(url, files=files, data=data, headers=headers)
        response.raise_for_status()
        payload = response.json()
        text = payload.get("text", "").strip()
        confidence = self._extract_confidence(payload)
        return text, confidence

    async def _transcribe_dashscope(
        self, audio_data: bytes, model: str
    ) -> tuple[str, float]:
        """DashScope Paraformer streaming ASR via SDK.

        Expects WAV 16kHz mono PCM input (frontend converts before upload).
        """
        api_key = self.api_key

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
                model=model or "paraformer-realtime-v2",
                format="wav",
                sample_rate=16000,
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

    def _extract_confidence(self, payload: dict[str, Any]) -> float:
        """Extract average confidence from Whisper response segments."""
        segments = payload.get("segments", [])
        if not segments:
            return 0.85  # default when no segments
        avg_conf = sum(seg.get("avg_logprob", -0.3) for seg in segments) / len(segments)
        # Convert logprob to rough confidence 0-1
        return max(0.0, min(1.0, 1.0 + avg_conf))

    # ------------------------------------------------------------------
    # Emotion detection from prosody (via LLM)
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def _detect_emotion(self, transcript: str, language: str) -> EmotionTag:
        """Use LLM to classify emotion from transcript context."""
        settings = get_settings()
        llm_key = settings.openai_api_key
        llm_base = settings.openai_base_url or "https://api.openai.com/v1"
        llm_model = settings.default_llm_model

        if not llm_key:
            logger.warning("asr.emotion.no_llm_key", fallback="neutral")
            return EmotionTag.NEUTRAL

        client = await self._get_client()
        prompt = _EMOTION_PROMPT.format(transcript=transcript, language=language)

        response = await client.post(
            f"{llm_base}/chat/completions",
            headers={"Authorization": f"Bearer {llm_key}", "Content-Type": "application/json"},
            json={
                "model": llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 20,
                "temperature": 0.0,
            },
        )
        response.raise_for_status()
        result = response.json()
        label = result["choices"][0]["message"]["content"].strip().lower()

        try:
            emotion = EmotionTag(label)
        except ValueError:
            logger.warning("asr.emotion.unknown_label", label=label, fallback="neutral")
            emotion = EmotionTag.NEUTRAL

        logger.info("asr.emotion.detected", emotion=emotion.value)
        return emotion
