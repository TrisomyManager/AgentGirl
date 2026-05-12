"""Tests for action_layer — router, generator_2d, lip_sync, sequencer, and API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from shared_contracts.models import ActionType, EmotionTag
from action_layer.generator_2d import Action2DGenerator
from action_layer.lip_sync import LipSyncGenerator, Viseme
from action_layer.main import create_app
from action_layer.router import ActionRouter
from action_layer.sequencer import ActionSequencer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_settings():
    with patch("shared.config.get_settings") as m_settings:
        settings = MagicMock()
        settings.action_provider = "tongyi"
        settings.action_api_key = None
        settings.action_base_url = None
        settings.avatar_2d_reference_url = "https://example.com/avatar.png"
        settings.log_level = "INFO"
        m_settings.return_value = settings
        yield settings


@pytest.fixture
def client(mock_settings):
    app = create_app()
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# ActionRouter
# ---------------------------------------------------------------------------

def test_resolve_action_type_from_intent():
    """Test intent-based action resolution."""
    assert ActionRouter.resolve_action_type("greet", EmotionTag.NEUTRAL) == ActionType.GESTURE_WAVE
    assert ActionRouter.resolve_action_type("agree", EmotionTag.SAD) == ActionType.GESTURE_NOD
    assert ActionRouter.resolve_action_type("think", EmotionTag.HAPPY) == ActionType.REACT_THINKING
    assert ActionRouter.resolve_action_type("listen", EmotionTag.ANGRY) == ActionType.LISTEN


def test_resolve_action_type_from_emotion():
    """Test emotion-based fallback resolution."""
    assert ActionRouter.resolve_action_type(None, EmotionTag.HAPPY) == ActionType.REACT_HAPPY
    assert ActionRouter.resolve_action_type(None, EmotionTag.SAD) == ActionType.REACT_SAD
    assert ActionRouter.resolve_action_type(None, EmotionTag.SURPRISED) == ActionType.REACT_SURPRISED
    assert ActionRouter.resolve_action_type(None, EmotionTag.CONCERNED) == ActionType.REACT_THINKING
    assert ActionRouter.resolve_action_type(None, EmotionTag.NEUTRAL) == ActionType.IDLE


def test_get_template():
    """Test template retrieval."""
    template = ActionRouter.get_template(ActionType.TALK)
    assert template["name"] == "talk"
    assert template["has_lip_sync"] is True
    assert template["loop"] is True

    idle_template = ActionRouter.get_template(ActionType.IDLE)
    assert idle_template["loop"] is True


def test_list_templates():
    """Test listing all templates."""
    templates = ActionRouter.list_templates()
    assert len(templates) == len(ActionType)
    talk = next(t for t in templates if t["action_type"] == "talk")
    assert talk["has_lip_sync"] is True


# ---------------------------------------------------------------------------
# LipSyncGenerator
# ---------------------------------------------------------------------------

def test_lip_sync_basic():
    """Test basic lip sync generation."""
    text = "hello world"
    duration_ms = 2000
    keyframes = LipSyncGenerator.generate(text, duration_ms, fps=12)

    assert len(keyframes) > 0
    assert keyframes[0]["timestamp_ms"] == 0
    assert keyframes[-1]["timestamp_ms"] == duration_ms
    assert all("viseme" in kf for kf in keyframes)


def test_lip_sync_empty_text():
    """Test lip sync with empty text."""
    keyframes = LipSyncGenerator.generate("", 1000, fps=12)
    assert len(keyframes) == 1
    assert keyframes[0]["viseme"] == Viseme.REST


def test_lip_sync_viseme_mapping():
    """Test that vowels map to correct visemes."""
    visemes = LipSyncGenerator._text_to_visemes("aeiou")
    # After collapsing consecutive duplicates, all 5 vowels should appear
    assert "A" in visemes
    assert "E" in visemes
    assert "I" in visemes
    assert "O" in visemes
    assert "U" in visemes


def test_lip_sync_consonant_mapping():
    """Test consonant viseme mapping."""
    visemes = LipSyncGenerator._text_to_visemes("bmp")
    assert all(v == Viseme.M for v in visemes)


def test_lip_sync_merge_with_frames():
    """Test merging lip sync into body frames."""
    body_frames = [
        {"timestamp_ms": 0, "image_url": "frame1.png"},
        {"timestamp_ms": 83, "image_url": "frame2.png"},
        {"timestamp_ms": 167, "image_url": "frame3.png"},
    ]
    lip_keyframes = [
        {"timestamp_ms": 0, "viseme": Viseme.REST},
        {"timestamp_ms": 100, "viseme": Viseme.A},
        {"timestamp_ms": 200, "viseme": Viseme.M},
    ]
    merged = LipSyncGenerator.merge_with_frames(body_frames, lip_keyframes)
    assert len(merged) == 3
    assert merged[0]["lip_shape"] == Viseme.REST
    assert merged[1]["lip_shape"] == Viseme.A
    assert merged[2]["lip_shape"] == Viseme.M


# ---------------------------------------------------------------------------
# Action2DGenerator (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_placeholder_frames(mock_settings):
    """Test placeholder frame generation."""
    gen = Action2DGenerator()
    result = await gen.generate(
        action_type=ActionType.TALK,
        emotion=EmotionTag.HAPPY,
        duration_ms=2000,
    )

    assert "frame_urls" in result
    assert "frame_timestamps_ms" in result
    assert result["total_duration_ms"] == 2000
    assert result["fps"] == 12
    assert len(result["frame_urls"]) == 24  # 2s * 12fps
    assert all("/static/actions/talk/" in url for url in result["frame_urls"])


@pytest.mark.asyncio
async def test_generate_with_reference_image(mock_settings):
    """Test generation with reference image URL."""
    gen = Action2DGenerator()
    result = await gen.generate(
        action_type=ActionType.REACT_HAPPY,
        emotion=EmotionTag.HAPPY,
        reference_image_url="https://example.com/ref.png",
        duration_ms=1000,
    )

    assert len(result["frame_urls"]) == 12
    assert result["frame_urls"][0].startswith("/static/actions/react_happy/")


# ---------------------------------------------------------------------------
# ActionSequencer (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_sequence(mock_settings):
    """Test full sequence building."""
    seq = ActionSequencer()
    sequence = await seq.build_sequence(
        turn_id="turn_001",
        action_type=ActionType.TALK,
        emotion=EmotionTag.HAPPY,
        text="你好",
        audio_duration_ms=1500,
    )

    assert sequence.turn_id == "turn_001"
    assert len(sequence.frames) > 0
    assert sequence.total_duration_ms == 1500
    # Lip sync should be present for TALK action
    assert any(f.lip_shape is not None for f in sequence.frames)


@pytest.mark.asyncio
async def test_build_sequence_no_text(mock_settings):
    """Test sequence without text (no lip sync)."""
    seq = ActionSequencer()
    sequence = await seq.build_sequence(
        turn_id="turn_002",
        action_type=ActionType.IDLE,
        emotion=EmotionTag.CALM,
        audio_duration_ms=1000,
    )

    assert sequence.turn_id == "turn_002"
    assert all(f.lip_shape is None for f in sequence.frames)


@pytest.mark.asyncio
async def test_build_sequence_intent_routing(mock_settings):
    """Test sequence with intent-based routing."""
    seq = ActionSequencer()
    sequence = await seq.build_sequence(
        turn_id="turn_003",
        action_type=None,
        emotion=EmotionTag.HAPPY,
        intent="greet",
        audio_duration_ms=1000,
    )

    assert sequence.frames[0].action_type == ActionType.GESTURE_WAVE


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

def test_list_templates_endpoint(client):
    """Test GET /action/templates."""
    response = client.get("/action/templates")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == len(ActionType)
    talk = next(t for t in data if t["action_type"] == "talk")
    assert talk["has_lip_sync"] is True


def test_lip_sync_endpoint(client):
    """Test POST /action/lip_sync."""
    response = client.post("/action/lip_sync", json={
        "text": "hello world",
        "duration_ms": 2000,
        "fps": 12,
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["timestamp_ms"] == 0
    assert data[-1]["timestamp_ms"] == 2000


def test_generate_endpoint(client):
    """Test POST /action/generate."""
    response = client.post("/action/generate", json={
        "turn_id": "turn_test_001",
        "emotion": "happy",
        "text": "你好呀",
        "audio_duration_ms": 1500,
        "intent": "greet",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["turn_id"] == "turn_test_001"
    assert len(data["frames"]) > 0
    assert data["total_duration_ms"] == 1500
