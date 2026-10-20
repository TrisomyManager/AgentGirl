import pytest
from pydantic import ValidationError

from avatar_runtime import build_avatar_timeline
from shared_contracts.avatar import AvatarTimeline


@pytest.mark.parametrize("duration", [None, -1, 120001, float("nan"), True])
def test_unknown_or_invalid_audio_durations_are_never_fabricated(duration):
    timeline = build_avatar_timeline(turn_id="t", duration_ms=duration)
    assert timeline.duration_ms is None
    assert timeline.clock == "audio_playback" and timeline.mouth_source == "audio_rms"


def test_emotion_gesture_and_offsets_are_bounded_and_renderer_independent():
    timeline = build_avatar_timeline(
        turn_id="t", segment_seq=3, duration_ms=1200, emotion={"primary": "affectionate", "intensity": 3}
    )
    assert timeline.cues[0].gesture == "nod" and timeline.cues[0].intensity == 1
    assert timeline.cues[0].offset_ms == 0 and timeline.duration_ms == 1200
    unknown = build_avatar_timeline(turn_id="t", emotion={"primary": "malformed", "intensity": float("inf")})
    assert unknown.cues[0].emotion == "neutral" and unknown.cues[0].intensity == 0.5
    assert AvatarTimeline.model_validate_json(timeline.model_dump_json()) == timeline
    with pytest.raises(ValidationError):
        build_avatar_timeline(turn_id="t", segment_seq=256)
