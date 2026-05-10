"""TTS client wrapper — Fish Audio S2 / ChatTTS / OpenAI TTS.

Accepts emotion tag and maps to voice parameters (speed, pitch, style).
Generates audio file, uploads to temp storage, returns URL.

Also provides ``synthesize_pcm_stream()`` for realtime voice pipelines that
need raw int16 PCM bytes without writing to disk.
"""

import base64
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shared_contracts.models import EmotionTag, VoiceSynthesisRequest
from shared_runtime.voice_runtime_config import get_runtime_voice_config
from voice_layer.audio_utils import get_audio_duration, save_temp_audio
from voice_layer.resolver import UnknownProviderError, resolve_voice
from voice_layer.voice_errors import VoiceConfigurationError

logger = structlog.get_logger("voice_layer.tts")

# ---------------------------------------------------------------------------
# Emotion → TTS parameter mapping
# ---------------------------------------------------------------------------

_EMOTION_VOICE_PARAMS: dict[EmotionTag, dict[str, Any]] = {
    EmotionTag.NEUTRAL:    {"speed": 1.0,  "pitch": 0.0,  "style": "neutral"},
    EmotionTag.HAPPY:      {"speed": 1.15, "pitch": 0.1,  "style": "cheerful"},
    EmotionTag.SAD:        {"speed": 0.85, "pitch": -0.1, "style": "sad"},
    EmotionTag.ANGRY:      {"speed": 1.1,  "pitch": 0.05, "style": "angry"},
    EmotionTag.SURPRISED:  {"speed": 1.2,  "pitch": 0.15, "style": "excited"},
    EmotionTag.FEARFUL:    {"speed": 1.05, "pitch": 0.08, "style": "terrified"},
    EmotionTag.DISGUSTED:  {"speed": 0.9,  "pitch": -0.05, "style": "unfriendly"},
    EmotionTag.AFFECTIONATE: {"speed": 0.95, "pitch": 0.02, "style": "gentle"},
    EmotionTag.CONCERNED:  {"speed": 0.92, "pitch": -0.02, "style": "serious"},
    EmotionTag.EXCITED:    {"speed": 1.25, "pitch": 0.12, "style": "excited"},
    EmotionTag.CALM:       {"speed": 0.88, "pitch": -0.03, "style": "calm"},
}


# ---------------------------------------------------------------------------
# TTS Client
# ---------------------------------------------------------------------------

class TTSClient:
    """Async TTS — configuration exclusively from ``voice_runtime_config`` (settings page)."""

    def __init__(self) -> None:
        self.timeout = 60.0
        self._client: httpx.AsyncClient | None = None
        self._load_from_runtime()

    def _load_from_runtime(self) -> None:
        rt = get_runtime_voice_config()
        self.provider = (rt.get("tts_provider") or "").strip().lower()
        self.api_key = (rt.get("tts_api_key") or "").strip()
        self.base_url = (rt.get("tts_base_url") or "").strip().rstrip("/")
        self.tts_model = (rt.get("tts_model") or "").strip()
        raw_voice = (rt.get("tts_voice_id") or "").strip()
        from voice_layer.resolver import _PROFILES  # type: ignore[attr-defined]

        self.raw_voice_override: str | None = None
        if raw_voice and raw_voice not in _PROFILES:
            self.raw_voice_override = raw_voice
            self.default_voice_profile_id = "default"
            logger.info("tts.using_native_voice_override", voice_id=raw_voice, provider=self.provider)
        else:
            self.default_voice_profile_id = raw_voice or "default"

    def _require_tts_config(self) -> None:
        if not self.provider:
            raise VoiceConfigurationError(
                "TTS 未配置：请在设置页选择提供商并保存。",
                code="tts_config_missing",
            )
        if not self.api_key or not self.base_url:
            raise VoiceConfigurationError(
                "TTS 未配置完整：请在设置页填写 API Key 与 Base URL 后保存。",
                code="tts_config_missing",
            )
        if not self.tts_model:
            raise VoiceConfigurationError(
                "TTS 模型未填写：请在设置页填写模型名称后保存。",
                code="tts_config_missing",
            )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Emotion → voice params
    # ------------------------------------------------------------------

    @staticmethod
    def map_emotion_to_params(emotion: EmotionTag) -> dict[str, Any]:
        """Map an EmotionTag to provider-agnostic voice parameters."""
        return _EMOTION_VOICE_PARAMS.get(emotion, _EMOTION_VOICE_PARAMS[EmotionTag.NEUTRAL]).copy()

    # ------------------------------------------------------------------
    # Synthesize
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def synthesize(self, request: VoiceSynthesisRequest) -> dict[str, Any]:
        """Synthesize speech and return audio URL + duration.

        Returns {"audio_url": str, "duration_ms": int, "local_path": str}
        """
        self._require_tts_config()
        t0 = time.perf_counter()
        host = urlparse(self.base_url).netloc or "unknown"
        params = self.map_emotion_to_params(request.emotion)
        speed = request.speed if request.speed != 1.0 else params["speed"]

        voice_profile_id = (
            getattr(request, "voice_profile_id", None)
            or request.voice_id
            or self.default_voice_profile_id
        )
        if self.raw_voice_override:
            voice_id = self.raw_voice_override
        else:
            voice_id = resolve_voice(self.provider, voice_profile_id, strict=True)
            if not voice_id:
                raise UnknownProviderError(self.provider, voice_profile_id)

        logger.info(
            "tts.synthesize.start",
            provider=self.provider,
            model=self.tts_model,
            base_url_host=host,
            profile_id=voice_profile_id,
            resolved_voice=voice_id,
            emotion=request.emotion.value,
            speed=speed,
            text_len=len(request.text),
        )

        if self.provider == "dashscope":
            result = await self._synthesize_dashscope(request.text, voice_id, speed, self.tts_model)
            logger.info(
                "tts.synthesize.end",
                provider=self.provider,
                model=self.tts_model,
                base_url_host=host,
                duration_ms=result["duration_ms"],
                audio_url=result["audio_url"],
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            return result
        if self.provider == "xiaomi_mimo":
            audio_data = await self._synthesize_xiaomi_mimo(request.text, voice_id, speed, params["style"])
        elif self.provider in ("openai", "siliconflow"):
            audio_data = await self._synthesize_openai(request.text, voice_id, speed, params["style"])
        elif self.provider == "fish_audio":
            audio_data = await self._synthesize_fish_audio(request.text, voice_id, speed, params)
        elif self.provider == "chattts":
            audio_data = await self._synthesize_chattts(request.text, voice_id, speed, params)
        else:
            raise ValueError(f"Unsupported TTS provider: {self.provider}")

        # Save to temp storage
        local_path = await save_temp_audio(audio_data, fmt="mp3")
        try:
            duration_sec = await get_audio_duration(audio_data, fmt="mp3")
        except Exception as exc:  # noqa: BLE001
            logger.warning("tts.duration_probe_failed", error=str(exc))
            duration_sec = 0.0
        duration_ms = int(duration_sec * 1000)

        # Build public URL (served by FastAPI StaticFiles → voice temp dir)
        audio_url = f"/static/voice/{Path(local_path).name}"

        logger.info(
            "tts.synthesize.end",
            provider=self.provider,
            model=self.tts_model,
            base_url_host=host,
            duration_ms=duration_ms,
            local_path=local_path,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        return {
            "audio_url": audio_url,
            "duration_ms": duration_ms,
            "local_path": local_path,
        }

    # ------------------------------------------------------------------
    # Realtime PCM streaming (no disk I/O)
    # ------------------------------------------------------------------

    async def synthesize_pcm_stream(self, text: str, *, sample_rate: int = 16000):
        """Synthesize speech and yield raw int16 PCM chunks.

        Yields PCM bytes incrementally so the realtime provider can push
        them to the browser without buffering the entire utterance first.

        - SiliconFlow / OpenAI: uses ``response_format=pcm`` directly →
          no ffmpeg needed.
        - DashScope / Fish Audio: fetches mp3, decodes to int16 PCM via
          pydub (ffmpeg required). Falls back to yielding the whole chunk
          if pydub/ffmpeg is unavailable.
        """
        self._require_tts_config()
        if self.provider == "xiaomi_mimo":
            async for chunk in self._synthesize_xiaomi_mimo_pcm_stream(text, sample_rate):
                yield chunk
        elif self.provider in ("openai", "siliconflow"):
            async for chunk in self._synthesize_openai_pcm_stream(text, sample_rate):
                yield chunk
        elif self.provider == "dashscope":
            async for chunk in self._synthesize_dashscope_pcm_stream(text, sample_rate):
                yield chunk
        elif self.provider == "fish_audio":
            async for chunk in self._synthesize_fish_audio_pcm_stream(text, sample_rate):
                yield chunk
        else:
            raise ValueError(f"Unsupported TTS provider for PCM stream: {self.provider}")

    async def _synthesize_openai_pcm_stream(self, text: str, sample_rate: int):
        logger = structlog.get_logger("voice_layer.tts.pcm_stream")
        model = self.tts_model
        voice_id = self.raw_voice_override or resolve_voice(self.provider, "default", strict=True)
        if not voice_id:
            raise UnknownProviderError(self.provider, "default")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "input": text,
            "voice": voice_id,
            "response_format": "pcm",
            "sample_rate": sample_rate,
        }
        url = f"{self.base_url}/audio/speech"
        async with httpx.AsyncClient(timeout=self.timeout) as stream_client, \
                stream_client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code >= 400:
                err_body = await resp.aread()
                snippet = err_body.decode("utf-8", errors="ignore")[:500]
                raise httpx.HTTPStatusError(
                    f"{self.provider} TTS PCM {resp.status_code}: {snippet}",
                    request=resp.request,
                    response=resp,
                )
            async for chunk in resp.aiter_bytes(chunk_size=4096):
                if chunk:
                    yield chunk
        logger.info("tts.pcm_stream.done", provider=self.provider, text_len=len(text))

    async def _synthesize_dashscope_pcm_stream(self, text: str, sample_rate: int):
        logger = structlog.get_logger("voice_layer.tts.pcm_stream")
        model = self.tts_model
        voice_id = self.raw_voice_override or resolve_voice(self.provider, "default", strict=True)
        if not voice_id:
            raise UnknownProviderError(self.provider, "default")
        result = await self._synthesize_dashscope(text, voice_id, 1.0, model)
        audio_url = result.get("audio_url", "")
        if not audio_url:
            raise ValueError(f"DashScope TTS returned no audio_url: {result}")
        mp3_bytes = await self._fetch_mp3(audio_url)
        async for chunk in self._mp3_to_pcm_chunks(mp3_bytes, sample_rate):
            yield chunk
        logger.info("tts.pcm_stream.done", provider=self.provider, text_len=len(text))

    async def _synthesize_fish_audio_pcm_stream(self, text: str, sample_rate: int):
        logger = structlog.get_logger("voice_layer.tts.pcm_stream")
        voice_id = self.raw_voice_override or resolve_voice(self.provider, "default", strict=True)
        if not voice_id:
            raise UnknownProviderError(self.provider, "default")
        mp3_bytes = await self._synthesize_fish_audio(text, voice_id, 1.0, {})
        async for chunk in self._mp3_to_pcm_chunks(mp3_bytes, sample_rate):
            yield chunk
        logger.info("tts.pcm_stream.done", provider=self.provider, text_len=len(text))

    async def _fetch_mp3(self, url: str) -> bytes:
        client = await self._get_client()
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content

    async def _mp3_to_pcm_chunks(self, mp3_bytes: bytes, sample_rate: int):
        """Convert mp3 bytes to int16 PCM chunks via pydub.

        Falls back to yielding the whole chunk as a single buffer if
        ffmpeg/pydub is not available.
        """
        logger = structlog.get_logger("voice_layer.tts.pcm_stream")
        try:
            import io as _io

            from pydub import AudioSegment
            audio = AudioSegment.from_file(_io.BytesIO(mp3_bytes), format="mp3")
            audio = audio.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
            pcm = audio.raw_data
            chunk_size = 4096
            for i in range(0, len(pcm), chunk_size):
                yield pcm[i:i + chunk_size]
        except Exception as exc:
            logger.warning("tts.mp3_to_pcm_failed", error=str(exc), fallback="raw_bytes")
            yield mp3_bytes

    # ------------------------------------------------------------------
    # Provider-specific implementations
    # ------------------------------------------------------------------

    async def _synthesize_openai(self, text: str, voice_id: str, speed: float, style: str) -> bytes:
        """OpenAI-compatible TTS endpoint (OpenAI / SiliconFlow / proxies)."""
        client = await self._get_client()
        model = self.tts_model
        host = urlparse(self.base_url).netloc or "unknown"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "input": text,
            "voice": voice_id,
            "speed": speed,
            "response_format": "mp3",
        }
        t_req = time.perf_counter()
        response = await client.post(f"{self.base_url}/audio/speech", headers=headers, json=payload)
        req_latency_ms = int((time.perf_counter() - t_req) * 1000)
        if response.status_code >= 400:
            body_preview = ""
            try:
                body_preview = response.text[:500]
            except Exception:  # noqa: BLE001
                pass
            logger.warning(
                "tts.openai_compatible.http_error",
                provider=self.provider,
                model=model,
                base_url_host=host,
                voice_id=voice_id,
                status=response.status_code,
                latency_ms=req_latency_ms,
                body_preview=body_preview[:200],
            )
            raise httpx.HTTPStatusError(
                f"{self.provider} TTS {response.status_code} (host={host}, model={model}, voice={voice_id}): {body_preview}",
                request=response.request,
                response=response,
            )
        return response.content

    async def _synthesize_dashscope(self, text: str, voice_id: str, speed: float, model: str) -> dict[str, Any]:
        """DashScope CosyVoice non-streaming API returning a hosted audio URL."""
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model,
            "input": {
                "text": text,
                "voice": voice_id,
                "format": "mp3",
                "sample_rate": 22050,
            },
        }
        if abs(speed - 1.0) > 1e-6:
            payload["input"]["rate"] = speed

        response = await client.post(f"{self.base_url}/services/audio/tts/SpeechSynthesizer", headers=headers, json=payload)
        if response.status_code >= 400:
            body_preview = ""
            try:
                body_preview = response.text[:400]
            except Exception:  # noqa: BLE001
                pass
            raise httpx.HTTPStatusError(
                f"DashScope TTS {response.status_code}: {body_preview}",
                request=response.request,
                response=response,
            )
        data = response.json()
        audio_url = (((data.get("output") or {}).get("audio") or {}).get("url")) or ""
        if not audio_url:
            raise ValueError(f"DashScope TTS response missing audio url: {data}")
        return {
            "audio_url": audio_url,
            "duration_ms": 0,
            "local_path": "",
        }

    async def _synthesize_fish_audio(self, text: str, voice_id: str, speed: float, params: dict[str, Any]) -> bytes:
        """Fish Audio S2 TTS."""
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "reference_id": voice_id,
            "speed": speed,
            "pitch": params.get("pitch", 0.0),
            "format": "mp3",
        }
        response = await client.post(f"{self.base_url}/tts", headers=headers, json=payload)
        response.raise_for_status()
        return response.content

    async def _synthesize_chattts(self, text: str, voice_id: str, speed: float, params: dict[str, Any]) -> bytes:
        """ChatTTS API."""
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "voice": voice_id,
            "speed": speed,
            "pitch": params.get("pitch", 0.0),
            "style": params.get("style", "neutral"),
            "format": "mp3",
        }
        response = await client.post(f"{self.base_url}/tts", headers=headers, json=payload)
        response.raise_for_status()
        return response.content

    # ------------------------------------------------------------------
    # Xiaomi MiMo TTS (chat-completions-based API)
    # ------------------------------------------------------------------

    def _build_mimo_messages(self, text: str, style: str, speed: float) -> list[dict[str, str]]:
        """Build MiMo TTS messages with optional style/speed hints in user role."""
        hints: list[str] = []
        if style and style not in ("neutral", "calm"):
            _STYLE_MAP = {
                "cheerful": "开心",
                "sad": "悲伤",
                "angry": "生气",
                "excited": "兴奋",
                "terrified": "恐惧",
                "unfriendly": "冷淡",
                "gentle": "温柔",
                "serious": "严肃",
            }
            mapped = _STYLE_MAP.get(style)
            if mapped:
                hints.append(mapped)
        if abs(speed - 1.0) > 0.05:
            hints.append("变快" if speed > 1.0 else "变慢")

        messages: list[dict[str, str]] = []
        if hints:
            messages.append({"role": "user", "content": "，".join(hints)})
        messages.append({"role": "assistant", "content": text})
        return messages

    async def _synthesize_xiaomi_mimo(self, text: str, voice_id: str, speed: float, style: str) -> bytes:
        """Xiaomi MiMo TTS via /v1/chat/completions with audio output."""
        client = await self._get_client()
        host = urlparse(self.base_url).netloc or "unknown"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.tts_model or "mimo-v2.5-tts",
            "messages": self._build_mimo_messages(text, style, speed),
            "audio": {
                "format": "mp3",
                "voice": voice_id,
            },
        }
        url = f"{self.base_url}/chat/completions"
        t_req = time.perf_counter()
        response = await client.post(url, headers=headers, json=payload)
        req_latency_ms = int((time.perf_counter() - t_req) * 1000)

        if response.status_code >= 400:
            body_preview = ""
            try:
                body_preview = response.text[:500]
            except Exception:  # noqa: BLE001
                pass
            logger.warning(
                "tts.xiaomi_mimo.http_error",
                model=self.tts_model,
                base_url_host=host,
                voice_id=voice_id,
                status=response.status_code,
                latency_ms=req_latency_ms,
                body_preview=body_preview[:200],
            )
            raise httpx.HTTPStatusError(
                f"xiaomi_mimo TTS {response.status_code} (host={host}, model={self.tts_model}, voice={voice_id}): {body_preview}",
                request=response.request,
                response=response,
            )

        resp_data = response.json()
        # MiMo returns audio in choices[0].message.audio.data (base64)
        choices = resp_data.get("choices") or []
        if choices:
            msg = choices[0].get("message", {})
            audio_obj = msg.get("audio", {})
            audio_b64 = audio_obj.get("data", "")
            if audio_b64:
                return base64.b64decode(audio_b64)
        # No audio data in the response — raise a clear error
        logger.warning("tts.xiaomi_mimo.no_audio_in_json", resp_keys=list(resp_data.keys()))
        raise ValueError(
            f"MiMo TTS response missing audio.data (voice={voice_id}, model={self.tts_model}). "
            f"Response keys: {list(resp_data.keys())}. Check API Key and voice ID."
        )

    async def _synthesize_xiaomi_mimo_pcm_stream(self, text: str, sample_rate: int):
        """MiMo TTS PCM stream — fetches audio then converts to PCM chunks."""
        logger = structlog.get_logger("voice_layer.tts.pcm_stream")
        voice_id = self.raw_voice_override or resolve_voice(self.provider, "default", strict=True)
        if not voice_id:
            raise UnknownProviderError(self.provider, "default")
        mp3_bytes = await self._synthesize_xiaomi_mimo(text, voice_id, 1.0, "neutral")
        async for chunk in self._mp3_to_pcm_chunks(mp3_bytes, sample_rate):
            yield chunk
        logger.info("tts.pcm_stream.done", provider=self.provider, text_len=len(text))
