"""Action sequencer — combines body animation + lip sync into ActionSequence.

Builds a complete ActionSequence from:
- ActionType (body animation template)
- EmotionTag
- TTS audio duration
- Optional text content (for lip sync)
- Optional reference image URL
"""

import uuid
from typing import Any

import structlog

from shared_contracts.models import ActionFrame, ActionSequence, ActionType, EmotionTag
from action_executor.action2d.generator_2d import Action2DGenerator
from action_executor.action2d.lip_sync import LipSyncGenerator
from action_executor.action2d.router import ActionRouter

logger = structlog.get_logger("action_executor.action2d.sequencer")


class ActionSequencer:
    """Orchestrate body animation, lip sync, and timeline assembly."""

    def __init__(self) -> None:
        self.generator = Action2DGenerator()
        self.lip_sync = LipSyncGenerator()
        self.router = ActionRouter()

    async def close(self) -> None:
        await self.generator.close()

    async def build_sequence(
        self,
        turn_id: str,
        action_type: ActionType | None,
        emotion: EmotionTag,
        text: str | None = None,
        audio_duration_ms: int = 2000,
        reference_image_url: str | None = None,
        intent: str | None = None,
    ) -> ActionSequence:
        """Build a complete ActionSequence.

        Args:
            turn_id: The conversation turn ID.
            action_type: Explicit action type; if None, resolved from intent+emotion.
            emotion: Companion's current emotion.
            text: Text content for lip sync (if talking).
            audio_duration_ms: TTS audio duration in milliseconds.
            reference_image_url: Reference image for 2D generation.
            intent: Optional intent string for action routing.

        Returns:
            ActionSequence with frames, total duration, and lip sync.
        """
        logger.info(
            "sequencer.build",
            turn_id=turn_id,
            emotion=emotion.value,
            audio_duration_ms=audio_duration_ms,
            has_text=bool(text),
        )

        # Resolve action type
        if action_type is None:
            action_type = self.router.resolve_action_type(intent, emotion)

        # Generate body animation frames
        body_result = await self.generator.generate(
            action_type=action_type,
            emotion=emotion,
            reference_image_url=reference_image_url,
            duration_ms=audio_duration_ms,
        )

        frame_urls = body_result["frame_urls"]
        frame_timestamps = body_result["frame_timestamps_ms"]
        fps = body_result["fps"]

        # Generate lip sync if text provided and action involves talking
        lip_keyframes: list[dict[str, Any]] = []
        if text and action_type in (ActionType.TALK, ActionType.LISTEN):
            lip_keyframes = self.lip_sync.generate(
                text=text,
                duration_ms=audio_duration_ms,
                fps=fps,
            )

        # Build ActionFrames
        frames: list[ActionFrame] = []
        for i, (url, ts) in enumerate(zip(frame_urls, frame_timestamps)):
            # Find lip shape for this timestamp
            lip_shape = self._find_lip_shape_at_timestamp(ts, lip_keyframes)

            frames.append(ActionFrame(
                frame_id=f"{turn_id}_frame_{i:04d}",
                action_type=action_type,
                image_url=url,
                lip_shape=lip_shape,
                duration_ms=int(1000 / fps),
                emotion=emotion,
            ))

        sequence = ActionSequence(
            sequence_id=str(uuid.uuid4()),
            turn_id=turn_id,
            frames=frames,
            total_duration_ms=audio_duration_ms,
        )

        logger.info(
            "sequencer.done",
            sequence_id=sequence.sequence_id,
            frame_count=len(frames),
            total_duration_ms=sequence.total_duration_ms,
        )
        return sequence

    @staticmethod
    def _find_lip_shape_at_timestamp(
        timestamp_ms: int,
        lip_keyframes: list[dict[str, Any]],
    ) -> str | None:
        """Find the appropriate lip shape for a given timestamp."""
        if not lip_keyframes:
            return None

        # Find the keyframe at or just before this timestamp
        best = lip_keyframes[0]
        for kf in lip_keyframes:
            if kf["timestamp_ms"] <= timestamp_ms:
                best = kf
            else:
                break
        return best["viseme"]
