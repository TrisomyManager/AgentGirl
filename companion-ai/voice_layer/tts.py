"""TTS client wrapper — Fish Audio S2 / ChatTTS / OpenAI TTS.

Accepts emotion tag and maps to voice parameters (speed, pitch, style).
Generates audio file, uploads to temp storage, returns URL.
"""

import io
import uuid
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shared.config import get_settings
from shared.models import EmotionTag, VoiceSynthesisRequest
from shared.voice_runtime_config import get_runtime_voice_config
from voice_layer.audio_utils import get_audio_duration, save_temp_audio

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
    """Async TTS client supporting Fish Audio S2, ChatTTS, and OpenAI TTS."""

    def __init__(self) -> None:
        settings = get_settings()
        rt = get_runtime_voice_config()
        self.provider = rt.get("tts_provider") or settings.tts_provider  # fish_audio | chattts | openai | siliconflow
        self.api_key = rt.get("tts_api_key") or settings.tts_api_key or settings.openai_api_key
        self.base_url = (
            rt.get("tts_base_url")
            or settings.tts_base_url
            or settings.openai_base_url
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.default_voice_id = rt.get("tts_voice_id") or settings.default_voice_id
        self.timeout = 60.0

        # Provider-specific defaults (only when no explicit base_url override)
        if not rt.get("tts_base_url") and not settings.tts_base_url:
            if self.provider == "fish_audio":
                self.base_url = "https://api.fish.audio/v1"
            elif self.provider == "chattts":
                self.base_url = "https://api.chattts.com/v1"
            elif self.provider == "siliconflow":
                self.base_url = "https://api.siliconflow.cn/v1"
            elif self.provider == "dashscope":
                self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            elif self.provider == "openai":
                self.base_url = "https://api.openai.com/v1"

        self._client: httpx.AsyncClient | None = None

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
        params = self.map_emotion_to_params(request.emotion)
        # Allow request-level override
        speed = request.speed if request.speed != 1.0 else params["speed"]
        voice_id = request.voice_id or self.default_voice_id

        logger.info(
            "tts.synthesize.start",
            provider=self.provider,
            emotion=request.emotion.value,
            speed=speed,
            text_len=len(request.text),
        )

        if self.provider in ("openai", "siliconflow", "dashscope"):
            audio_data = await self._synthesize_openai(request.text, voice_id, speed, params["style"])
        elif self.provider == "fish_audio":
            audio_data = await self._synthesize_fish_audio(request.text, voice_id, speed, params)
        elif self.provider == "chattts":
            audio_data = await self._synthesize_chattts(request.text, voice_id, speed, params)
        else:
            raise ValueError(f"Unsupported TTS provider: {self.provider}")

        # Save to temp storage
        local_path = await save_temp_audio(audio_data, fmt="mp3")
        duration_sec = await get_audio_duration(audio_data, fmt="mp3")
        duration_ms = int(duration_sec * 1000)

        # Build public URL (in production, serve via static file server or CDN)
        audio_url = f"/static/voice/{local_path.split('/')[-1]}"

        logger.info(
            "tts.synthesize.end",
            provider=self.provider,
            duration_ms=duration_ms,
            local_path=local_path,
        )

        return {
            "audio_url": audio_url,
            "duration_ms": duration_ms,
            "local_path": local_path,
        }

    # ------------------------------------------------------------------
    # Provider-specific implementations
    # ------------------------------------------------------------------

    async def _synthesize_openai(self, text: str, voice_id: str, speed: float, style: str) -> bytes:
        """OpenAI-compatible TTS endpoint (OpenAI / SiliconFlow / proxies)."""
        client = await self._get_client()
        rt = get_runtime_voice_config()
        # Allow user to override the TTS model from frontend
        if rt.get("tts_model"):
            model = rt["tts_model"]
        elif self.provider == "siliconflow":
            model = "FunAudioLLM/CosyVoice2-0.5B"
        elif self.provider == "dashscope":
            model = "cosyvoice-v1"
        else:
            model = "tts-1"
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
        response = await client.post(f"{self.base_url}/audio/speech", headers=headers, json=payload)
        response.raise_for_status()
        return response.content

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
