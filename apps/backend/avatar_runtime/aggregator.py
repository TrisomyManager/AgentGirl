"""Aggregate bounded emotion/action cues onto a segment's audio clock.

Mouth movement uses actual waveform energy in the renderer, not guessed phonemes.
Unknown provider durations remain unknown until the audio player supplies them.
"""

import math

from shared_contracts.avatar import AvatarCue, AvatarTimeline

_EMOTIONS = frozenset(
    {
        "neutral",
        "calm",
        "happy",
        "excited",
        "sad",
        "angry",
        "surprised",
        "fearful",
        "disgusted",
        "affectionate",
        "concerned",
    }
)
_GESTURES = {
    "happy": "brighten",
    "excited": "brighten",
    "affectionate": "nod",
    "surprised": "tilt",
    "concerned": "tilt",
    "sad": "tilt",
}


def build_avatar_timeline(*, turn_id: str, segment_seq: int = 0, duration_ms=None, emotion=None) -> AvatarTimeline:
    state = emotion if isinstance(emotion, dict) else {}
    tag = state.get("primary", "neutral")
    if not isinstance(tag, str) or tag not in _EMOTIONS:
        tag = "neutral"
    intensity = state.get("intensity", 0.5)
    if not isinstance(intensity, (int, float)) or not math.isfinite(intensity):
        intensity = 0.5
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or not 0 <= duration_ms <= 120_000:
        duration_ms = None
    return AvatarTimeline(
        turn_id=turn_id,
        segment_seq=segment_seq,
        duration_ms=duration_ms,
        cues=[
            AvatarCue(offset_ms=0, emotion=tag, intensity=max(0, min(1, intensity)), gesture=_GESTURES.get(tag, "idle"))
        ],
    )
