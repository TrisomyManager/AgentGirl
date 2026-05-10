"""ASR client — reads only ``shared_runtime.voice_runtime_config`` (settings page).

OpenAI-compatible providers (SiliconFlow, Groq, OpenAI) use ``POST /audio/transcriptions``.
DashScope uses the adapter when ``asr_base_url`` indicates Aliyun/DashScope.
"""

from __future__ import annotations

import contextlib
import io
import struct
import time
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shared_contracts.models import EmotionTag, VoiceTranscriptionResult
from shared_runtime.llm_client import get_runtime_llm_config
from shared_runtime.voice_runtime_config import get_runtime_voice_config
from voice_layer.voice_errors import VoiceConfigurationError

logger = structlog.get_logger("voice_layer.asr")

_EMOTION_PROMPT = """You are an emotion classifier. Given a transcript and optional context, classify the speaker's primary emotion.

Available emotions: neutral, happy, sad, angry, surprised, fearful, disgusted, affectionate, concerned, excited, calm

Transcript: {transcript}
Language: {language}

Respond with ONLY the emotion label (lowercase)."""

# Reject obvious empty / mis-tap uploads (very small bodies are unlikely to be valid speech).
_MIN_AUDIO_BYTES = 2048


def _base_url_host(base_url: str) -> str:
    try:
        return urlparse(base_url).netloc or "unknown"
    except Exception:
        return "unknown"


class ASRClient:
    """Async ASR — configuration exclusively from runtime voice JSON / memory."""

    def __init__(self) -> None:
        self.timeout = 60.0
        self._client: httpx.AsyncClient | None = None
        self._load_from_runtime()

    def _load_from_runtime(self) -> None:
        rt = get_runtime_voice_config()
        self.api_key = (rt.get("asr_api_key") or "").strip()
        self.base_url = (rt.get("asr_base_url") or "").strip().rstrip("/")
        self.default_model = (rt.get("asr_model") or "").strip()
        self.provider = self._infer_provider(self.base_url)

    @staticmethod
    def _infer_provider(base_url: str) -> str:
        if not base_url:
            return "unset"
        bl = base_url.lower()
        if "dashscope" in bl or "aliyuncs" in bl:
            return "dashscope"
        if "groq" in bl:
            return "groq"
        if "siliconflow" in bl:
            return "siliconflow"
        return "openai_compat"

    def _require_asr_config(self) -> None:
        if not self.api_key or not self.base_url or not self.default_model:
            raise VoiceConfigurationError(
                "ASR 未配置完整：请在设置页填写 API Key、Base URL 和模型后保存。",
                code="asr_config_missing",
            )
        if self.provider == "unset":
            raise VoiceConfigurationError(
                "ASR Base URL 无效：请填写 SiliconFlow 或其他兼容服务的 Base URL。",
                code="asr_config_missing",
            )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _pcm_to_wav(pcm_int16: bytes, sample_rate: int = 16000) -> bytes:
        data_size = len(pcm_int16)
        header = bytearray(44)
        header[0:4] = b"RIFF"
        struct.pack_into("<I", header, 4, 36 + data_size)
        header[8:12] = b"WAVE"
        header[12:16] = b"fmt "
        struct.pack_into("<I", header, 16, 16)
        struct.pack_into("<H", header, 20, 1)
        struct.pack_into("<H", header, 22, 1)
        struct.pack_into("<I", header, 24, sample_rate)
        struct.pack_into("<I", header, 28, sample_rate * 2)
        struct.pack_into("<H", header, 32, 2)
        struct.pack_into("<H", header, 34, 16)
        header[36:40] = b"data"
        struct.pack_into("<I", header, 40, data_size)
        return bytes(header) + pcm_int16

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def transcribe_pcm(self, pcm_int16: bytes, sample_rate: int = 16000) -> str:
        """Transcribe raw int16 PCM via OpenAI-compatible ``/audio/transcriptions`` or DashScope."""
        self._require_asr_config()
        if len(pcm_int16) < _MIN_AUDIO_BYTES:
            raise VoiceConfigurationError(
                "音频过短，无法识别。请说话时间稍长一些。",
                code="asr_audio_too_short",
            )
        t0 = time.perf_counter()
        model = self.default_model
        host = _base_url_host(self.base_url)

        if self.provider == "dashscope":
            wav = self._pcm_to_wav(pcm_int16, sample_rate)
            from voice_layer.providers.dashscope import transcribe_dashscope

            text, _conf = await transcribe_dashscope(
                wav, api_key=self.api_key, model=model, sample_rate=sample_rate
            )
            text = text.strip()
            logger.info(
                "asr.transcribe_pcm.end",
                provider=self.provider,
                model=model,
                base_url_host=host,
                pcm_bytes=len(pcm_int16),
                text_len=len(text),
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            return text

        wav = self._pcm_to_wav(pcm_int16, sample_rate)
        client = await self._get_client()
        files = {"file": ("audio.wav", io.BytesIO(wav), "audio/wav")}
        data = {
            "model": model,
            "language": "zh",
            "response_format": "json",
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/audio/transcriptions"
        response = await client.post(url, files=files, data=data, headers=headers)
        if response.status_code >= 400:
            body_preview = ""
            with contextlib.suppress(Exception):
                body_preview = response.text[:500]
            raise httpx.HTTPStatusError(
                f"ASR {response.status_code}: {body_preview}",
                request=response.request,
                response=response,
            )
        payload = response.json()
        text = payload.get("text", "").strip()
        logger.info(
            "asr.transcribe_pcm.end",
            provider=self.provider,
            model=model,
            base_url_host=host,
            pcm_bytes=len(pcm_int16),
            upload_mime="audio/wav",
            text_len=len(text),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        return text

    @staticmethod
    def _upload_tuple(
        audio_data: bytes,
        *,
        upload_filename: str | None,
        upload_content_type: str | None,
    ) -> tuple[str, io.BytesIO, str]:
        name = (upload_filename or "audio.wav").lower()
        ct = (upload_content_type or "").split(";")[0].strip().lower()
        if name.endswith(".wav") or ct == "audio/wav" or ct == "audio/wave":
            return "audio.wav", io.BytesIO(audio_data), "audio/wav"
        if name.endswith(".webm") or ct == "audio/webm":
            return "audio.webm", io.BytesIO(audio_data), "audio/webm"
        if name.endswith(".mp3") or ct == "audio/mpeg" or ct == "audio/mp3":
            return "audio.mp3", io.BytesIO(audio_data), "audio/mpeg"
        return "audio.bin", io.BytesIO(audio_data), ct or "application/octet-stream"

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
        *,
        upload_filename: str | None = None,
        upload_content_type: str | None = None,
    ) -> VoiceTranscriptionResult:
        self._require_asr_config()
        if len(audio_data) < _MIN_AUDIO_BYTES:
            raise VoiceConfigurationError(
                "音频过短，无法识别。请说话时间稍长一些。",
                code="asr_audio_too_short",
            )
        model = model or self.default_model
        host = _base_url_host(self.base_url)
        fname, bio, mime = self._upload_tuple(
            audio_data,
            upload_filename=upload_filename,
            upload_content_type=upload_content_type,
        )
        t0 = time.perf_counter()
        logger.info(
            "asr.transcribe.start",
            provider=self.provider,
            model=model,
            language=language,
            base_url_host=host,
            audio_bytes=len(audio_data),
            upload_mime=mime,
            upload_filename=fname,
        )

        if self.provider == "dashscope":
            text, confidence = await self._transcribe_dashscope(audio_data, model)
        else:
            text, confidence = await self._transcribe_openai_compat(
                audio_data, model, language, upload_filename=fname, upload_content_type=mime
            )

        logger.info(
            "asr.transcribe.end",
            provider=self.provider,
            model=model,
            base_url_host=host,
            text_len=len(text),
            confidence=confidence,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        detected_emotion = await self._detect_emotion(text, language)
        duration_ms = len(audio_data) // 32

        return VoiceTranscriptionResult(
            text=text,
            confidence=confidence,
            detected_emotion=detected_emotion,
            language=language,
            duration_ms=duration_ms,
        )

    async def _transcribe_openai_compat(
        self,
        audio_data: bytes,
        model: str,
        language: str,
        *,
        upload_filename: str,
        upload_content_type: str,
    ) -> tuple[str, float]:
        client = await self._get_client()
        whisper_lang = language.split("-")[0] if language.lower().startswith("zh") else language
        files = {
            "file": (upload_filename, io.BytesIO(audio_data), upload_content_type),
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

    async def _transcribe_dashscope(self, audio_data: bytes, model: str) -> tuple[str, float]:
        from voice_layer.providers.dashscope import transcribe_dashscope

        return await transcribe_dashscope(audio_data, api_key=self.api_key, model=model)

    def _extract_confidence(self, payload: dict[str, Any]) -> float:
        segments = payload.get("segments", [])
        if not segments:
            return 0.85
        avg_conf = sum(seg.get("avg_logprob", -0.3) for seg in segments) / len(segments)
        return max(0.0, min(1.0, 1.0 + avg_conf))

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def _detect_emotion(self, transcript: str, language: str) -> EmotionTag:
        """LLM 情感仅使用设置页保存的 LLM 运行时配置，不读取 .env 里的 OpenAI key。"""
        llm = get_runtime_llm_config()
        llm_key = (llm.get("openai_api_key") or "").strip()
        llm_base = (llm.get("openai_base_url") or "").strip().rstrip("/")
        llm_model = (llm.get("default_model") or "").strip()
        if not llm_key or not llm_base or not llm_model:
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
        return emotion
