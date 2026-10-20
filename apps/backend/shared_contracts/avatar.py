"""Renderer-independent presentation timeline, anchored to actual audio playback."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AvatarCue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset_ms: int = Field(ge=0, le=120_000)
    emotion: str = Field(max_length=32)
    intensity: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    gesture: Literal["idle", "nod", "tilt", "brighten"] = "idle"


class AvatarTimeline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    turn_id: str = Field(max_length=128)
    segment_seq: int = Field(ge=0, le=255)
    duration_ms: int | None = Field(default=None, ge=0, le=120_000)
    clock: Literal["audio_playback"] = "audio_playback"
    mouth_source: Literal["audio_rms"] = "audio_rms"
    cues: list[AvatarCue] = Field(max_length=32)
