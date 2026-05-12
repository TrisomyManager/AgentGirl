"""Tests for voice_layer — ASR, TTS, audio_utils, and API endpoints."""

import io
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg not on PATH (pydub export requires it)",
)
from fastapi.testclient import TestClient

from shared_contracts.models import EmotionTag, VoiceSynthesisRequest
from voice_layer.asr import ASRClient
from voice_layer.audio_utils import convert_audio_format, get_audio_duration, save_temp_audio
from voice_layer.main import create_app
from voice_layer.tts import TTSClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_settings():
    cfg = {
        "asr_api_key": "test-asr-key",
        "asr_base_url": "https://api.siliconflow.cn/v1",
        "asr_model": "FunAudioLLM/SenseVoiceSmall",
        "tts_provider": "openai",
        "tts_api_key": "test-tts-key",
        "tts_base_url": "https://api.openai.com/v1",
        "tts_model": "tts-1",
        "tts_voice_id": "alloy",
    }
    llm = {
        "openai_api_key": "llm-key",
        "openai_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    }
    with patch("voice_layer.asr.get_runtime_voice_config", return_value=dict(cfg)), \
         patch("voice_layer.tts.get_runtime_voice_config", return_value=dict(cfg)), \
         patch("voice_layer.asr.get_runtime_llm_config", return_value=llm):
        yield cfg


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

@_requires_ffmpeg
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


@_requires_ffmpeg
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
    with patch("voice_layer.audio_utils.get_voice_temp_directory", return_value=tmp_path):
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

        result = await asr.transcribe(
            b"x" * 3000,
            language="zh-CN",
            upload_filename="a.wav",
            upload_content_type="audio/wav",
        )
        assert result.text == "你好，今天天气不错"
        assert result.detected_emotion == EmotionTag.HAPPY
        assert result.confidence > 0.0
        assert result.language == "zh-CN"


# ---------------------------------------------------------------------------
# API endpoints (mocked)
# ---------------------------------------------------------------------------

@_requires_ffmpeg
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


def test_static_voice_mp3_served(mock_settings, tmp_path):
    """TTS URLs under /static/voice must be readable (Windows-safe paths)."""
    from fastapi import FastAPI

    from voice_layer.voice_static import mount_voice_static_files

    sample = tmp_path / "abc123.mp3"
    sample.write_bytes(b"\xff\xfb\x90\x00")  # minimal mp3-like bytes

    with patch("voice_layer.audio_utils.get_voice_temp_directory", return_value=tmp_path):
        app = FastAPI()
        mount_voice_static_files(app)
        with TestClient(app) as tc:
            resp = tc.get("/static/voice/abc123.mp3")
            assert resp.status_code == 200
            assert resp.content.startswith(b"\xff\xfb")


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


# ---------------------------------------------------------------------------
# Xiaomi MiMo TTS provider tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mimo_settings():
    cfg = {
        "asr_api_key": "test-asr-key",
        "asr_base_url": "https://api.siliconflow.cn/v1",
        "asr_model": "FunAudioLLM/SenseVoiceSmall",
        "tts_provider": "xiaomi_mimo",
        "tts_api_key": "test-mimo-key",
        "tts_base_url": "https://api.xiaomimimo.com/v1",
        "tts_model": "mimo-v2.5-tts",
        "tts_voice_id": "default_zh",
    }
    llm = {
        "openai_api_key": "llm-key",
        "openai_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    }
    with patch("voice_layer.tts.get_runtime_voice_config", return_value=dict(cfg)), \
         patch("voice_layer.asr.get_runtime_voice_config", return_value=dict(cfg)), \
         patch("voice_layer.asr.get_runtime_llm_config", return_value=llm):
        yield cfg


def test_mimo_request_body_generation(mimo_settings):
    """Verify MiMo TTS builds the correct chat-completions request body."""
    tts = TTSClient()
    assert tts.provider == "xiaomi_mimo"
    assert tts.tts_model == "mimo-v2.5-tts"

    messages = tts._build_mimo_messages("你好呀", "cheerful", 1.0)
    # Should have user hint + assistant text
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert "开心" in messages[0]["content"]
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "你好呀"


def test_mimo_request_body_no_hints(mimo_settings):
    """MiMo request with neutral style and default speed has no user message."""
    tts = TTSClient()
    messages = tts._build_mimo_messages("测试", "neutral", 1.0)
    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
    assert messages[0]["content"] == "测试"


def test_mimo_request_body_speed_hint(mimo_settings):
    """MiMo request with non-default speed adds speed hint."""
    tts = TTSClient()
    messages = tts._build_mimo_messages("测试", "neutral", 1.3)
    assert len(messages) == 2
    assert "变快" in messages[0]["content"]


@pytest.mark.asyncio
async def test_mimo_audio_base64_decode(mimo_settings):
    """MiMo TTS correctly decodes base64 audio from choices[0].message.audio.data."""
    import base64

    tts = TTSClient()
    fake_audio = b"\xff\xfb\x90\x00" * 100
    fake_b64 = base64.b64encode(fake_audio).decode()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "audio": {"data": fake_b64},
            },
        }],
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(tts, "_get_client", new_callable=AsyncMock) as mock_factory:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        mock_factory.return_value = mock_client

        result = await tts._synthesize_xiaomi_mimo("测试", "default_zh", 1.0, "neutral")
        assert result == fake_audio
        assert len(result) > 0

        # Verify the request was sent to the correct endpoint
        call_args = mock_client.post.call_args
        assert "/chat/completions" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["model"] == "mimo-v2.5-tts"
        assert payload["audio"]["voice"] == "default_zh"
        assert payload["audio"]["format"] == "mp3"


@pytest.mark.asyncio
async def test_mimo_empty_audio_raises(mimo_settings):
    """MiMo TTS raises ValueError when audio.data is empty or missing."""
    import base64

    tts = TTSClient()

    # Case 1: base64 data exists but decodes to empty bytes
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "audio": {"data": base64.b64encode(b"").decode()},
            },
        }],
    }

    with patch.object(tts, "_get_client", new_callable=AsyncMock) as mock_factory:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        mock_factory.return_value = mock_client

        # empty b64 encodes to "" which is falsy → falls through to missing error
        with pytest.raises(ValueError, match="missing audio.data"):
            await tts._synthesize_xiaomi_mimo("测试", "default_zh", 1.0, "neutral")

    # Case 2: no audio key in response
    mock_response2 = MagicMock()
    mock_response2.status_code = 200
    mock_response2.json.return_value = {"choices": [{"message": {}}]}

    with patch.object(tts, "_get_client", new_callable=AsyncMock) as mock_factory2:
        mock_client2 = AsyncMock()
        mock_client2.post = AsyncMock(return_value=mock_response2)
        mock_client2.is_closed = False
        mock_factory2.return_value = mock_client2

        with pytest.raises(ValueError, match="missing audio.data"):
            await tts._synthesize_xiaomi_mimo("测试", "default_zh", 1.0, "neutral")


def test_mimo_voice_id_priority(mimo_settings):
    """Settings page tts_voice_id takes priority over persona mapping."""
    tts = TTSClient()
    # tts_voice_id is "default_zh" — not a known profile name, so raw_voice_override
    assert tts.raw_voice_override == "default_zh"
    assert tts.default_voice_profile_id == "default"


def test_mimo_voice_id_profile_fallback(mimo_settings):
    """When tts_voice_id is a known profile name, resolver is used."""
    cfg = dict(mimo_settings)
    cfg["tts_voice_id"] = "xiaonuan"  # known profile
    with patch("voice_layer.tts.get_runtime_voice_config", return_value=cfg):
        tts = TTSClient()
        assert tts.raw_voice_override is None
        assert tts.default_voice_profile_id == "xiaonuan"

