"""Tests for voice_layer — ASR, TTS, audio_utils, and API endpoints."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from shared.models import EmotionTag, VoiceSynthesisRequest
from voice_layer.api import router
from voice_layer.asr import ASRClient
from voice_layer.audio_utils import convert_audio_format, get_audio_duration, save_temp_audio
from voice_layer.main import create_app
from voice_layer.tts import TTSClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_settings():
    with patch("voice_layer.asr.get_settings") as m_asr, \
         patch("voice_layer.tts.get_settings") as m_tts, \
         patch("voice_layer.audio_utils.get_settings") as m_au:
        settings = MagicMock()
        settings.whisper_api_key = "test-whisper-key"
        settings.whisper_base_url = "https://api.openai.com/v1"
        settings.openai_api_key = "test-openai-key"
        settings.openai_base_url = "https://api.openai.com/v1"
        settings.default_llm_model = "gpt-4o"
        settings.tts_provider = "openai"
        settings.tts_api_key = "test-tts-key"
        settings.tts_base_url = None
        settings.default_voice_id = "zh-CN-XiaoxiaoNeural"
        settings.log_level = "INFO"
        m_asr.return_value = settings
        m_tts.return_value = settings
        m_au.return_value = settings
        yield settings


@pytest.fixture
def client(mock_settings):
    app = create_app()
    # Inject mock clients via lifespan is hard in sync TestClient;
    # instead patch the module-level variables after lifespan runs.
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# Audio utils
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_audio_duration(mock_settings):
    """Test duration detection with a silent MP3."""
    # Build a 1-second silent MP3 via pydub
    from pydub import AudioSegment
    silent = AudioSegment.silent(duration=1000)
    buf = io.BytesIO()
    silent.export(buf, format="mp3")
    audio_bytes = buf.getvalue()

    duration = await get_audio_duration(audio_bytes, fmt="mp3")
    assert 0.9 <= duration <= 1.2


@pytest.mark.asyncio
async def test_convert_audio_format(mock_settings):
    """Test audio format conversion."""
    from pydub import AudioSegment
    silent = AudioSegment.silent(duration=500)
    buf = io.BytesIO()
    silent.export(buf, format="wav")
    wav_bytes = buf.getvalue()

    mp3_bytes = await convert_audio_format(wav_bytes, source_fmt="wav", target_fmt="mp3")
    assert len(mp3_bytes) > 0
    assert mp3_bytes != wav_bytes


@pytest.mark.asyncio
async def test_save_temp_audio(mock_settings, tmp_path):
    """Test saving audio to temp directory."""
    with patch("voice_layer.audio_utils._get_temp_dir", return_value=tmp_path):
        path = await save_temp_audio(b"fake_audio_data", fmt="mp3")
        assert path.endswith(".mp3")
        assert (tmp_path / path.split("/")[-1]).exists()


# ---------------------------------------------------------------------------
# TTS emotion mapping
# ---------------------------------------------------------------------------

def test_emotion_to_params():
    """Verify emotion-to-voice-parameter mapping."""
    happy = TTSClient.map_emotion_to_params(EmotionTag.HAPPY)
    assert happy["speed"] == 1.15
    assert happy["pitch"] == 0.1

    sad = TTSClient.map_emotion_to_params(EmotionTag.SAD)
    assert sad["speed"] == 0.85
    assert sad["pitch"] == -0.1

    affectionate = TTSClient.map_emotion_to_params(EmotionTag.AFFECTIONATE)
    assert affectionate["speed"] == 0.95
    assert affectionate["style"] == "gentle"


# ---------------------------------------------------------------------------
# ASR client (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_asr_transcribe(mock_settings):
    """Test ASR transcription with mocked HTTP response."""
    asr = ASRClient()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "text": "你好，今天天气不错",
        "segments": [{"avg_logprob": -0.15}],
    }
    mock_response.raise_for_status = MagicMock()

    mock_llm_response = MagicMock()
    mock_llm_response.json.return_value = {
        "choices": [{"message": {"content": "happy"}}],
    }
    mock_llm_response.raise_for_status = MagicMock()

    with patch.object(asr, "_get_client", new_callable=AsyncMock) as mock_client_factory:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[mock_response, mock_llm_response])
        mock_client_factory.return_value = mock_client

        result = await asr.transcribe(b"fake_audio", language="zh-CN")
        assert result.text == "你好，今天天气不错"
        assert result.detected_emotion == EmotionTag.HAPPY
        assert result.confidence > 0.0
        assert result.language == "zh-CN"


# ---------------------------------------------------------------------------
# API endpoints (mocked)
# ---------------------------------------------------------------------------

def test_transcribe_endpoint(client):
    """Test POST /voice/transcribe."""
    mock_result = MagicMock()
    mock_result.text = "测试文本"
    mock_result.confidence = 0.92
    mock_result.detected_emotion = EmotionTag.NEUTRAL
    mock_result.language = "zh-CN"
    mock_result.duration_ms = 1234
    mock_result.speaker_id = None

    with patch("voice_layer.api._get_asr") as mock_get_asr:
        mock_asr = AsyncMock()
        mock_asr.transcribe = AsyncMock(return_value=mock_result)
        mock_get_asr.return_value = mock_asr

        # Build a minimal valid MP3
        from pydub import AudioSegment
        silent = AudioSegment.silent(duration=500)
        buf = io.BytesIO()
        silent.export(buf, format="mp3")

        response = client.post(
            "/voice/transcribe",
            files={"audio": ("test.mp3", buf.getvalue(), "audio/mpeg")},
            data={"language": "zh-CN"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "测试文本"
        assert data["detected_emotion"] == "neutral"


def test_synthesize_endpoint(client):
    """Test POST /voice/synthesize."""
    with patch("voice_layer.api._get_tts") as mock_get_tts:
        mock_tts = AsyncMock()
        mock_tts.synthesize = AsyncMock(return_value={
            "audio_url": "/static/voice/abc123.mp3",
            "duration_ms": 2500,
            "local_path": "/tmp/companion_voice/abc123.mp3",
        })
        mock_get_tts.return_value = mock_tts

        request = VoiceSynthesisRequest(
            text="你好",
            emotion=EmotionTag.HAPPY,
            language="zh-CN",
        )
        response = client.post("/voice/synthesize", json=request.model_dump())
        assert response.status_code == 200
        data = response.json()
        assert data["audio_url"] == "/static/voice/abc123.mp3"
        assert data["duration_ms"] == 2500
