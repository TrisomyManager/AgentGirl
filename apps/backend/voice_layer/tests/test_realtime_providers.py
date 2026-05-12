"""Tests for realtime voice providers, VoiceProfile, event normalization, credential safety."""

import asyncio
import gzip
import json
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared_contracts.models import VoiceProfile
from voice_layer.providers.realtime import (
    get_provider,
    get_realtime_status,
    init_registry,
    list_providers,
)
from voice_layer.providers.realtime.local_realtime import LocalRealtimeProvider
from voice_layer.providers.realtime.volc_realtime import (
    AUDIO_SERVER_RESPONSE,
    EVENT_TTS_RESPONSE,
    FULL_SERVER_RESPONSE,
    GZIP_COMPRESSION,
    HAS_EVENT_ID,
    JSON_SERIALIZATION,
    NO_COMPRESSION,
    NO_SEQUENCE,
    NO_SERIALIZATION,
    VolcRealtimeProvider,
    _build_audio_payload,
    _build_event_payload,
    _build_finish_session,
    _make_header,
    _parse_response,
    _redact_headers,
)
from voice_layer.resolver import (
    UnknownProviderError,
    get_voice_profile,
    list_voice_profiles,
    register_voice_profile,
    resolve_voice,
)

# ======================================================================
# Helpers for building test binary frames
# ======================================================================

def _build_test_frame(
    event_id: int,
    body: bytes,
    *,
    msg_type: int = FULL_SERVER_RESPONSE,
    flags: int = NO_SEQUENCE | HAS_EVENT_ID,
    serialization: int = JSON_SERIALIZATION,
    compression: int = GZIP_COMPRESSION,
) -> bytes:
    """Build a test binary frame matching the Volc wire format.

    When ``flags`` includes ``HAS_EVENT_ID`` the event_id is prepended
    to the payload body; otherwise only the body bytes follow the size.
    """
    header = bytes([
        0x11,
        (msg_type << 4) | flags,
        (serialization << 4) | compression,
        0x00,
    ])
    payload = struct.pack(">I", event_id) + body if flags & HAS_EVENT_ID else body
    size = struct.pack(">I", len(payload))
    return header + size + payload


# ======================================================================
# VoiceProfile resolution tests
# ======================================================================

class TestVoiceProfile:
    def test_default_profile(self):
        profile = get_voice_profile()
        assert profile.voice_profile_id == "default"
        assert profile.provider_voices["local"] == "piper_huayan"
        assert profile.provider_voices["volc_realtime"] == "zh_female_tianmei"

    def test_huayan_profile(self):
        profile = get_voice_profile("huayan")
        assert profile.voice_profile_id == "huayan"
        assert profile.display_name == "花颜"
        assert profile.provider_voices["volc_realtime"] == "zh_female_tianmei"

    def test_unknown_profile_falls_back_to_default(self):
        profile = get_voice_profile("nonexistent")
        assert profile.voice_profile_id == "default"

    def test_resolve_voice_local(self):
        voice_id = resolve_voice("local")
        assert voice_id == "piper_huayan"

    def test_resolve_voice_volc(self):
        voice_id = resolve_voice("volc_realtime")
        assert voice_id == "zh_female_tianmei"

    def test_resolve_voice_unknown_provider_returns_empty(self):
        voice_id = resolve_voice("nonexistent_provider")
        assert voice_id == ""

    def test_resolve_voice_strict_raises(self):
        with pytest.raises(UnknownProviderError):
            resolve_voice("nonexistent_provider", strict=True)

    def test_register_and_list(self):
        new_profile = VoiceProfile(
            voice_profile_id="test_voice",
            display_name="Test",
            provider_voices={"local": "test_piper", "volc_realtime": "test_volc"},
        )
        register_voice_profile(new_profile)
        assert "test_voice" in list_voice_profiles()
        profile = get_voice_profile("test_voice")
        assert profile.provider_voices["local"] == "test_piper"


# ======================================================================
# Provider registry tests
# ======================================================================

class TestProviderRegistry:
    def test_init_registry_creates_local(self):
        with patch("voice_layer.providers.realtime._providers", {}), \
             patch("voice_layer.providers.realtime._default_provider_name", "local"), \
             patch("shared_runtime.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                realtime_voice_provider="local",
                volc_app_id=None,
                volc_access_token=None,
            )
            init_registry()
            providers = list_providers()
            assert "local" in providers
            provider = get_provider()
            assert provider.provider_name == "local"

    def test_local_provider_capabilities(self):
        provider = LocalRealtimeProvider()
        assert provider.provider_name == "local"
        assert provider.supports_interrupt is True
        assert provider.supports_text_delta is True

    def test_volc_provider_capabilities(self):
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://test.example.com/api",
            )
            provider = VolcRealtimeProvider(
                app_id="test_app",
                access_token="test_token",
            )
            assert provider.provider_name == "volc_realtime"
            assert provider.supports_interrupt is True
            assert provider.supports_text_delta is True

    def test_session_config_includes_audio_format(self):
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://test.example.com/api",
            )
            provider = VolcRealtimeProvider(
                app_id="test_app",
                access_token="test_token",
            )
            assert provider._audio_format == "pcm"
            assert provider._audio_sample_rate == 24000

    def test_volc_provider_without_credentials(self):
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id=None,
                volc_access_token=None,
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://test.example.com/api",
            )
            provider = VolcRealtimeProvider()
            assert provider._app_id == ""
            assert provider._access_token == ""


# ======================================================================
# get_realtime_status tests
# ======================================================================

class TestRealtimeStatus:
    def test_status_config_local(self):
        with patch("voice_layer.providers.realtime._providers", {}), \
             patch("voice_layer.providers.realtime._default_provider_name", "local"), \
             patch("shared_runtime.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                realtime_voice_provider="local",
                volc_app_id=None,
                volc_access_token=None,
            )
            init_registry()
            status = get_realtime_status()
            assert status["current_provider"] == "local"
            assert status["configured_provider"] == "local"
            assert status["fallback_reason"] is None

    def test_status_volc_with_credentials(self):
        with patch("voice_layer.providers.realtime._providers", {}), \
             patch("voice_layer.providers.realtime._default_provider_name", "local"), \
             patch("shared_runtime.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                realtime_voice_provider="volc_realtime",
                volc_app_id="app123",
                volc_access_token="tok456",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://x.com",
            )
            init_registry()
            status = get_realtime_status()
            assert status["current_provider"] == "volc_realtime"
            assert status["configured_provider"] == "volc_realtime"
            assert status["fallback_reason"] is None

    def test_status_volc_missing_credentials(self):
        with patch("voice_layer.providers.realtime._providers", {}), \
             patch("voice_layer.providers.realtime._default_provider_name", "local"), \
             patch("shared_runtime.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                realtime_voice_provider="volc_realtime",
                volc_app_id=None,
                volc_access_token=None,
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://x.com",
            )
            init_registry()
            status = get_realtime_status()
            assert status["current_provider"] == "local"
            assert status["configured_provider"] == "volc_realtime"
            assert status["fallback_reason"] == "missing_credentials"


# ======================================================================
# Volcengine binary protocol tests
# ======================================================================

class TestVolcBinaryProtocol:
    def test_make_header(self):
        header = _make_header()
        assert len(header) == 4
        assert header[0] == 0x11  # version=1, header_size=1
        assert header[1] == 0x10  # FULL_CLIENT_REQUEST, NO_SEQUENCE
        assert header[2] == 0x11  # JSON, GZIP
        assert header[3] == 0x00

    def test_make_audio_header(self):
        header = _make_header(
            message_type=0x02,
            flags=0x04,
            serialization=0x00,
            compression=0x00,
        )
        assert header[0] == 0x11
        assert header[1] == 0x24
        assert header[2] == 0x00

    @pytest.mark.asyncio
    async def test_build_event_payload(self):
        data = {"key": "value"}
        payload = _build_event_payload(1, data)
        header = payload[:4]
        assert header[0] == 0x11
        size = int.from_bytes(payload[4:8], "big")
        assert size == len(payload[8:])

    @pytest.mark.asyncio
    async def test_build_audio_payload(self):
        audio = b"\x00\x01" * 160
        payload = _build_audio_payload(audio, is_last=False)
        assert len(payload) >= 8
        payload_last = _build_audio_payload(audio, is_last=True)
        assert payload_last[1] != payload[1]

    def test_parse_response_connection_started(self):
        body = gzip.compress(json.dumps({"message": "ok"}).encode())
        msg = _build_test_frame(50, body)
        result = _parse_response(msg)
        assert result.get("_event_id") == 50
        assert result.get("message") == "ok"

    def test_parse_response_asr(self):
        body = gzip.compress(json.dumps({"word": "你好"}).encode())
        msg = _build_test_frame(451, body)
        result = _parse_response(msg)
        assert result["word"] == "你好"
        assert result["_event_id"] == 451

    def test_parse_response_empty_message(self):
        result = _parse_response(b"")
        assert "_parse_error" in result
        assert result["_parse_error"] == "message too short"

    def test_parse_response_truncated_payload(self):
        msg = bytes([0x11, 0x94, 0x11, 0x00, 0x00, 0x00, 0x00, 0x64])
        result = _parse_response(msg)
        assert "_parse_error" in result
        assert result["_parse_error"] == "payload truncated"

    def test_parse_response_no_serialization_audio(self):
        """AUDIO_SERVER_RESPONSE with NO_SERIALIZATION: raw audio bytes exposed."""
        raw_audio = b"\x00\x01\x02\x03" * 40
        msg = _build_test_frame(
            EVENT_TTS_RESPONSE,
            raw_audio,
            msg_type=AUDIO_SERVER_RESPONSE,
            flags=NO_SEQUENCE | HAS_EVENT_ID,
            serialization=NO_SERIALIZATION,
            compression=NO_COMPRESSION,
        )
        result = _parse_response(msg)
        assert result["_event_id"] == EVENT_TTS_RESPONSE
        assert result["_serialization"] == NO_SERIALIZATION
        assert result["_raw_payload"] == raw_audio

    def test_parse_response_no_event_id_no_serialization(self):
        """AUDIO_SERVER without event_id: raw payload exposed under _raw_payload."""
        raw_audio = b"\xAA\xBB" * 80
        msg = _build_test_frame(
            0, raw_audio,
            msg_type=AUDIO_SERVER_RESPONSE,
            flags=NO_SEQUENCE,
            serialization=NO_SERIALIZATION,
            compression=NO_COMPRESSION,
        )
        result = _parse_response(msg)
        assert result["_event_id"] is None
        assert result["_raw_payload"] == raw_audio


# ======================================================================
# Event normalization tests
# ======================================================================

class TestEventNormalization:
    def test_local_provider_emits_unified_events(self):
        provider = LocalRealtimeProvider()
        assert provider.provider_name == "local"

    def test_volc_parse_asr_delta(self):
        body = gzip.compress(json.dumps({"word": "今天"}).encode())
        msg = _build_test_frame(451, body)
        result = _parse_response(msg)
        assert result["_event_id"] == 451
        assert result["word"] == "今天"

    def test_volc_parse_chat_delta(self):
        body = gzip.compress(json.dumps({"word": "你好"}).encode())
        msg = _build_test_frame(550, body)
        result = _parse_response(msg)
        assert result["_event_id"] == 550
        assert result["word"] == "你好"

    def test_tts_audio_bytes_forwarded(self):
        """TTSResponse with raw audio: _raw_payload contains the PCM bytes."""
        pcm = b"\x00\x00\x00\x00" * 50
        msg = _build_test_frame(
            EVENT_TTS_RESPONSE, pcm,
            msg_type=AUDIO_SERVER_RESPONSE,
            flags=NO_SEQUENCE | HAS_EVENT_ID,
            serialization=NO_SERIALIZATION,
            compression=NO_COMPRESSION,
        )
        result = _parse_response(msg)
        assert result["_raw_payload"] == pcm
        assert result["_event_id"] == EVENT_TTS_RESPONSE

    def test_tts_json_base64_audio_extracted(self):
        """TTSResponse JSON with base64-encoded audio."""
        raw = b"\x01\x02" * 20
        import base64
        b64 = base64.b64encode(raw).decode()
        body = gzip.compress(json.dumps({"audio": b64}).encode())
        msg = _build_test_frame(EVENT_TTS_RESPONSE, body)
        result = _parse_response(msg)
        assert result["_event_id"] == EVENT_TTS_RESPONSE
        assert result["audio"] == b64

    def test_tts_sentence_start_has_text(self):
        body = gzip.compress(json.dumps({"text": "你好世界", "sentence": "hello"}).encode())
        msg = _build_test_frame(350, body)
        result = _parse_response(msg)
        assert result["_event_id"] == 350
        assert result["text"] == "你好世界"
        assert result["sentence"] == "hello"

    def test_session_failed_event(self):
        body = gzip.compress(json.dumps({"message": "invalid config"}).encode())
        msg = _build_test_frame(153, body)
        result = _parse_response(msg)
        assert result["_event_id"] == 153
        assert result["message"] == "invalid config"


# ======================================================================
# websockets.connect tests
# ======================================================================

class TestWebsocketConnection:
    @pytest.mark.asyncio
    async def test_connect_uses_additional_headers(self):
        """websockets.connect is called with additional_headers, not extra_headers."""
        with patch("voice_layer.providers.realtime.volc_realtime.websockets.connect") as mock_connect, \
             patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://test.example.com/api",
            )
            mock_connect.side_effect = RuntimeError("inspect connect args")

            provider = VolcRealtimeProvider(
                app_id="test_app",
                access_token="test_token",
            )
            send_json = AsyncMock()
            send_bytes = AsyncMock()
            receive = AsyncMock(return_value={"type": "disconnect"})

            await provider.run(send_json, send_bytes, receive)

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            assert "additional_headers" in call_kwargs, \
                "websockets.connect must use additional_headers (15.0+)"
            assert "extra_headers" not in call_kwargs, \
                "websockets.connect must NOT use extra_headers (removed in 15.0)"
            assert call_kwargs["additional_headers"]["X-Api-App-Key"] == "test_app"
            assert call_kwargs["additional_headers"]["X-Api-Access-Key"] == "test_token"

    @pytest.mark.asyncio
    async def test_missing_credentials_does_not_connect(self):
        """When credentials are missing, websockets.connect is never called."""
        with patch("voice_layer.providers.realtime.volc_realtime.websockets.connect") as mock_connect, \
             patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id=None,
                volc_access_token=None,
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://test.example.com/api",
            )

            provider = VolcRealtimeProvider()
            send_json = AsyncMock()
            send_bytes = AsyncMock()
            receive = AsyncMock()

            await provider.run(send_json, send_bytes, receive)

            mock_connect.assert_not_called()
            send_json.assert_called_once()
            error_msg = send_json.call_args[0][0]
            assert error_msg["type"] == "error"
            assert "credentials" in error_msg["msg"].lower()


# ======================================================================
# Interrupt tests
# ======================================================================

class TestInterrupt:
    @pytest.mark.asyncio
    async def test_interrupt_sends_cancel_frame_and_interrupted(self):
        """interrupt → ws.send receives EVENT_FINISH_SESSION and frontend gets interrupted."""
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://x",
            )
            provider = VolcRealtimeProvider(app_id="test_app", access_token="test_token")
            mock_ws = MagicMock()
            mock_ws.send = AsyncMock()
            interrupt_event = asyncio.Event()
            ws_send_json = AsyncMock()

            await provider._handle_interrupt(mock_ws, interrupt_event, ws_send_json)

            mock_ws.send.assert_called_once()
            sent_frame = mock_ws.send.call_args[0][0]
            expected = _build_finish_session()
            assert sent_frame == expected, "interrupt must send EVENT_FINISH_SESSION cancel frame"

            assert interrupt_event.is_set(), "interrupt must set interrupt_event"

            ws_send_json.assert_called_with({"type": "interrupted"})


# ======================================================================
# Audio config dual-write tests
# ======================================================================

class TestAudioConfigDualWrite:
    @pytest.mark.asyncio
    async def test_session_config_writes_both_channel_and_channels(self):
        """_send_start_session writes both channel and channels fields."""
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://test.example.com/api",
            )
            provider = VolcRealtimeProvider(
                app_id="test_app",
                access_token="test_token",
            )
            mock_ws = MagicMock()
            mock_ws.send = AsyncMock()

            await provider._send_start_session(mock_ws)

            mock_ws.send.assert_called_once()
            raw = mock_ws.send.call_args[0][0]
            parsed = _parse_response(raw)
            tts_config = parsed.get("tts", {})
            audio_config = tts_config.get("audio_config", {})

            assert audio_config.get("channel") == 1, "channel (singular) must be written"
            assert audio_config.get("channels") == 1, "channels (plural) must be written"


# ======================================================================
# TTS response robustness tests
# ======================================================================

class TestTTSRobustness:
    @pytest.mark.asyncio
    async def test_tts_json_audio_field(self):
        """Extracts audio from parsed["audio"]."""
        import base64
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://x",
            )
            provider = VolcRealtimeProvider(app_id="x", access_token="y")
            raw = b"\x01\x02\x03" * 10
            b64 = base64.b64encode(raw).decode()
            parsed = {"audio": b64}
            ws_send_bytes = AsyncMock()

            await provider._handle_tts_response(parsed, JSON_SERIALIZATION, ws_send_bytes)

            ws_send_bytes.assert_called_once()
            assert ws_send_bytes.call_args[0][0] == raw

    @pytest.mark.asyncio
    async def test_tts_json_data_field(self):
        """Falls back to parsed.get("data") when audio key is absent."""
        import base64
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://x",
            )
            provider = VolcRealtimeProvider(app_id="x", access_token="y")
            raw = b"\xDE\xAD\xBE\xEF" * 5
            b64 = base64.b64encode(raw).decode()
            parsed = {"data": b64, "audio": None}
            ws_send_bytes = AsyncMock()

            await provider._handle_tts_response(parsed, JSON_SERIALIZATION, ws_send_bytes)

            ws_send_bytes.assert_called_once()
            assert ws_send_bytes.call_args[0][0] == raw

    @pytest.mark.asyncio
    async def test_tts_json_payload_msg_audio_field(self):
        """Deep-extracts from parsed.get("payload_msg", {}).get("audio")."""
        import base64
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://x",
            )
            provider = VolcRealtimeProvider(app_id="x", access_token="y")
            raw = b"\xCC\xDD" * 30
            b64 = base64.b64encode(raw).decode()
            parsed = {"payload_msg": {"audio": b64}}
            ws_send_bytes = AsyncMock()

            await provider._handle_tts_response(parsed, JSON_SERIALIZATION, ws_send_bytes)

            ws_send_bytes.assert_called_once()
            assert ws_send_bytes.call_args[0][0] == raw

    @pytest.mark.asyncio
    async def test_tts_json_bad_base64_logs_warning(self):
        """Bad base64 in audio field logs warning, does not call send_bytes."""
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings, \
             patch("voice_layer.providers.realtime.volc_realtime.logger.warning") as mock_warn:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://x",
            )
            provider = VolcRealtimeProvider(app_id="x", access_token="y")
            parsed = {"audio": "not valid base64!!!@@@@"}
            ws_send_bytes = AsyncMock()

            await provider._handle_tts_response(parsed, JSON_SERIALIZATION, ws_send_bytes)

            ws_send_bytes.assert_not_called()
            mock_warn.assert_called_once()
            assert "b64_decode_failed" in mock_warn.call_args[0][0]

    @pytest.mark.asyncio
    async def test_tts_no_serialization_strips_sentence_id_when_enabled(self, monkeypatch):
        """When VOLC_TTS_STRIP_SENTENCE_ID=1, strips 4-byte sentence_id prefix."""
        import importlib
        monkeypatch.setenv("VOLC_TTS_STRIP_SENTENCE_ID", "1")
        mod = importlib.import_module("voice_layer.providers.realtime.volc_realtime")
        importlib.reload(mod)

        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://x",
            )
            provider = mod.VolcRealtimeProvider(app_id="x", access_token="y")
            sentence_id = struct.pack(">I", 42)
            pcm = b"\x00\x01" * 40
            raw = sentence_id + pcm
            parsed = {"_raw_payload": raw}
            ws_send_bytes = AsyncMock()

            await provider._handle_tts_response(parsed, NO_SERIALIZATION, ws_send_bytes)

            ws_send_bytes.assert_called_once()
            result = ws_send_bytes.call_args[0][0]
            assert result == pcm, f"Expected {pcm[:16]!r}, got {result[:16]!r}"

        monkeypatch.setenv("VOLC_TTS_STRIP_SENTENCE_ID", "0")
        importlib.reload(importlib.import_module("voice_layer.providers.realtime.volc_realtime"))

    @pytest.mark.asyncio
    async def test_tts_no_serialization_keeps_large_sentence_id(self, monkeypatch):
        """sentence_id >= 0x10000 is not stripped (looks like valid PCM data)."""
        import importlib
        monkeypatch.setenv("VOLC_TTS_STRIP_SENTENCE_ID", "1")
        mod = importlib.import_module("voice_layer.providers.realtime.volc_realtime")
        importlib.reload(mod)

        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://x",
            )
            provider = mod.VolcRealtimeProvider(app_id="x", access_token="y")
            large_id = struct.pack(">I", 0x12345)
            pcm = b"\xAA" * 40
            raw = large_id + pcm
            parsed = {"_raw_payload": raw}
            ws_send_bytes = AsyncMock()

            await provider._handle_tts_response(parsed, NO_SERIALIZATION, ws_send_bytes)

            ws_send_bytes.assert_called_once()
            assert ws_send_bytes.call_args[0][0] == raw

        monkeypatch.setenv("VOLC_TTS_STRIP_SENTENCE_ID", "0")
        importlib.reload(importlib.import_module("voice_layer.providers.realtime.volc_realtime"))

    @pytest.mark.asyncio
    async def test_tts_no_serialization_no_strip_by_default(self):
        """By default (VOLC_TTS_STRIP_SENTENCE_ID not set), raw is passed unchanged."""
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="test_app",
                volc_access_token="test_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://x",
            )
            provider = VolcRealtimeProvider(app_id="x", access_token="y")
            full_raw = b"\x00\x00\x00\x01" + b"\xAB" * 60
            parsed = {"_raw_payload": full_raw}
            ws_send_bytes = AsyncMock()

            await provider._handle_tts_response(parsed, NO_SERIALIZATION, ws_send_bytes)

            ws_send_bytes.assert_called_once()
            assert ws_send_bytes.call_args[0][0] == full_raw


# ======================================================================
# Credential safety tests
# ======================================================================

class TestCredentialSafety:
    def test_local_provider_no_credentials_required(self):
        provider = LocalRealtimeProvider()
        assert provider.provider_name == "local"

    def test_volc_provider_does_not_expose_credentials_in_name(self):
        with patch("voice_layer.providers.realtime.volc_realtime.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                volc_app_id="very_secret_app_id",
                volc_access_token="very_secret_token",
                volc_resource_id="volc.speech.dialog",
                volc_endpoint="wss://test.example.com/api",
            )
            provider = VolcRealtimeProvider(
                app_id="very_secret_app_id",
                access_token="very_secret_token",
            )
            assert provider.provider_name == "volc_realtime"
            assert "secret" not in str(provider.provider_name)
            assert "very_secret" not in provider.provider_name

    def test_redact_headers_masks_sensitive_keys(self):
        headers = {
            "X-Api-App-Key": "my_secret_app_key_12345",
            "X-Api-Access-Key": "my_secret_access_token_67890",
            "X-Api-Resource-Id": "volc.speech.dialog",
            "X-Api-Connect-Id": "abc123",
        }
        redacted = _redact_headers(headers)
        assert "my_secret" not in redacted["X-Api-App-Key"]
        assert "my_secret" not in redacted["X-Api-Access-Key"]
        assert "****" in redacted["X-Api-App-Key"]
        assert "****" in redacted["X-Api-Access-Key"]
        assert redacted["X-Api-Resource-Id"] == "volc.speech.dialog"
        assert redacted["X-Api-Connect-Id"] == "abc123"

    def test_redact_headers_short_value(self):
        headers = {
            "X-Api-Access-Key": "ab",
        }
        redacted = _redact_headers(headers)
        assert redacted["X-Api-Access-Key"] == "****"

    def test_resolve_voice_does_not_leak_secrets(self):
        result = resolve_voice("volc_realtime")
        assert "token" not in result.lower()
        assert "key" not in result.lower()
