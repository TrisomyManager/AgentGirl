"""2D action generation — calls external API (placeholder for MVP).

Input: reference image URL + action description + emotion
Output: animated frame sequence URLs

For MVP, generates placeholder frame sequences with timing info.
"""

import uuid
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shared_runtime.config import get_settings
from shared_contracts.models import ActionType, EmotionTag

logger = structlog.get_logger("action_executor.action2d.generator_2d")


# ---------------------------------------------------------------------------
# 2D Action Generator
# ---------------------------------------------------------------------------

class Action2DGenerator:
    """Generate 2D animated frame sequences from reference image + action description.

    For MVP, falls back to placeholder frame URLs when API is unavailable.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.provider = settings.action_provider  # tongyi | custom
        self.api_key = settings.action_api_key
        self.base_url = settings.action_base_url
        self.reference_image_url = settings.avatar_2d_reference_url
        self.timeout = 60.0
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        action_type: ActionType,
        emotion: EmotionTag,
        reference_image_url: str | None = None,
        duration_ms: int = 2000,
    ) -> dict[str, Any]:
        """Generate a 2D action frame sequence.

        Returns:
            {
                "frame_urls": [str],
                "frame_timestamps_ms": [int],
                "total_duration_ms": int,
                "fps": int,
            }
        """
        ref_url = reference_image_url or self.reference_image_url
        description = self._build_description(action_type, emotion)

        logger.info(
            "generator_2d.start",
            provider=self.provider,
            action=action_type.value,
            emotion=emotion.value,
            duration_ms=duration_ms,
        )

        # Try external API if configured
        if self.api_key and self.base_url:
            try:
                result = await self._call_external_api(ref_url, description, emotion, duration_ms)
                logger.info("generator_2d.external_ok", frame_count=len(result["frame_urls"]))
                return result
            except Exception as exc:
                logger.warning("generator_2d.external_failed", error=str(exc), fallback="placeholder")

        # MVP fallback: placeholder frames
        result = self._generate_placeholder_frames(action_type, duration_ms)
        logger.info("generator_2d.placeholder", frame_count=len(result["frame_urls"]))
        return result

    # ------------------------------------------------------------------
    # External API call (placeholder)
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _call_external_api(
        self,
        reference_image_url: str | None,
        description: str,
        emotion: EmotionTag,
        duration_ms: int,
    ) -> dict[str, Any]:
        """Call external 2D generation API (e.g. Tongyi Wanxiang).

        This is a placeholder implementation. Replace with actual API schema.
        """
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "wan2.2-animate-move",
            "reference_image_url": reference_image_url,
            "prompt": description,
            "emotion": emotion.value,
            "duration_ms": duration_ms,
            "fps": 12,
            "format": "png_sequence",
        }

        response = await client.post(f"{self.base_url}/generate", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        # Expected response shape (placeholder):
        # {"frame_urls": [...], "frame_timestamps_ms": [...], "total_duration_ms": int, "fps": int}
        return {
            "frame_urls": data.get("frame_urls", []),
            "frame_timestamps_ms": data.get("frame_timestamps_ms", []),
            "total_duration_ms": data.get("total_duration_ms", duration_ms),
            "fps": data.get("fps", 12),
        }

    # ------------------------------------------------------------------
    # Placeholder frame generation
    # ------------------------------------------------------------------

    def _generate_placeholder_frames(self, action_type: ActionType, duration_ms: int) -> dict[str, Any]:
        """Generate placeholder frame URLs for MVP."""
        fps = 12
        frame_count = max(1, int((duration_ms / 1000) * fps))
        frame_urls = [
            f"/static/actions/{action_type.value}/frame_{i:03d}.png"
            for i in range(frame_count)
        ]
        frame_timestamps_ms = [
            int((i / fps) * 1000) for i in range(frame_count)
        ]
        return {
            "frame_urls": frame_urls,
            "frame_timestamps_ms": frame_timestamps_ms,
            "total_duration_ms": duration_ms,
            "fps": fps,
        }

    # ------------------------------------------------------------------
    # Description builder
    # ------------------------------------------------------------------

    def _build_description(self, action_type: ActionType, emotion: EmotionTag) -> str:
        """Build a natural-language action description for the generation API."""
        descriptions = {
            ActionType.IDLE: f"{emotion.value} idle breathing pose, subtle body movement",
            ActionType.TALK: f"{emotion.value} talking pose, natural body language while speaking",
            ActionType.LISTEN: f"{emotion.value} attentive listening pose, slight head movement",
            ActionType.REACT_HAPPY: f"{emotion.value} happy reaction, smiling, slight bounce",
            ActionType.REACT_SAD: f"{emotion.value} sad reaction, drooping shoulders, looking down",
            ActionType.REACT_SURPRISED: f"{emotion.value} surprised reaction, widening eyes, leaning back",
            ActionType.REACT_THINKING: f"{emotion.value} thinking pose, hand to chin, gazing upward",
            ActionType.GESTURE_WAVE: f"{emotion.value} waving gesture, friendly arm movement",
            ActionType.GESTURE_NOD: f"{emotion.value} nodding gesture, affirmative head movement",
            ActionType.GESTURE_HEAD_TILT: f"{emotion.value} curious head tilt, inquisitive expression",
        }
        return descriptions.get(action_type, f"{emotion.value} pose")
