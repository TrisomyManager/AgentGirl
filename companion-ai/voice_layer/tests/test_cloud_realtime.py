"""Tests for CloudRealtimeProvider — mocked cloud ASR / LLM / TTS."""

import asyncio
import contextlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_layer.providers.realtime.cloud_realtime import CloudRealtimeProvider


async def _fake_llm_stream(history):
    yield "今天"
    yield "天气"
    yield "不错"
    yield "，"
    yield "适合"
    yield "出去"
    yield "走走"
    yield "。"


async def _fake_tts_chunks(text: str, *, sample_rate: int = 16000):
    sentence_bytes = text.encode("utf-8")
    pcm = sentence_bytes + b"\x00" * (len(sentence_bytes) % 2)
    for i in range(0, len(pcm), 2):
        yield pcm[i:i + 2]


class TestCloudRealtimeProvider:
    def test_provider_capabilities(self):
        provider = CloudRealtimeProvider()
        assert provider.provider_name == "cloud"
        assert provider.supports_interrupt is True
        assert provider.supports_text_delta is True


class TestCloudRealtimeFlow:
    @pytest.mark.asyncio
    async def test_full_turn(self):
        audio_done_seen = False
        text_final_seen = False
        text_delta_seen = False
        sentence_start_seen = False
        binary_seen = False

        receive_queue: asyncio.Queue = asyncio.Queue()

        async def _send_json(data: dict):
            nonlocal audio_done_seen, text_final_seen, text_delta_seen, sentence_start_seen
            t = data.get("type")
            if t == "user_transcript_final":
                text_final_seen = True
            elif t == "assistant_text_delta":
                text_delta_seen = True
            elif t == "assistant_sentence_start":
                sentence_start_seen = True
            elif t == "assistant_audio_done" and not audio_done_seen:
                audio_done_seen = True
                receive_queue.put_nowait({"type": "disconnect"})

        async def _send_bytes(data: bytes):
            nonlocal binary_seen
            binary_seen = True

        async def _receive():
            return await receive_queue.get()

        await receive_queue.put({"type": "text", "data": json.dumps({"type": "start"})})
        await receive_queue.put({"type": "binary", "data": b"\x00\x01\x02\x03" * 100})
        await receive_queue.put({"type": "text", "data": json.dumps({"type": "speech_end"})})

        mock_asr = AsyncMock()
        mock_asr.transcribe_pcm = AsyncMock(return_value="你好，今天天气怎么样？")

        mock_tts = AsyncMock()

        async def _mock_tts_stream(text, *, sample_rate=16000):
            async for c in _fake_tts_chunks(text, sample_rate=sample_rate):
                yield c

        mock_tts.synthesize_pcm_stream = _mock_tts_stream

        with patch("voice_layer.providers.realtime.cloud_realtime.ASRClient", return_value=mock_asr), \
             patch("voice_layer.providers.realtime.cloud_realtime.TTSClient", return_value=mock_tts), \
             patch("voice_layer.providers.realtime.cloud_realtime._stream_llm") as mock_llm:

            mock_llm.side_effect = _fake_llm_stream

            provider = CloudRealtimeProvider()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    provider.run(
                        ws_send_json=_send_json,
                        ws_send_bytes=_send_bytes,
                        ws_receive=_receive,
                    ),
                    timeout=3.0,
                )

        assert text_final_seen, "Should receive user_transcript_final"
        assert text_delta_seen, "Should receive at least one assistant_text_delta"
        assert sentence_start_seen, "Should receive at least one assistant_sentence_start"
        assert binary_seen, "Should receive at least one binary audio chunk"
        assert audio_done_seen, "Should receive assistant_audio_done"

    @pytest.mark.asyncio
    async def test_turn_completion_schedules_memory_sync(self):
        receive_queue: asyncio.Queue = asyncio.Queue()
        sync_calls: list[tuple[str, str]] = []

        async def _send_json(data: dict):
            del data

        async def _send_bytes(data: bytes):
            del data

        async def _receive():
            return await receive_queue.get()

        def _capture_sync(**kwargs):
            sync_calls.append((kwargs.get("user_message", ""), kwargs.get("assistant_message", "")))
            receive_queue.put_nowait({"type": "disconnect"})

        await receive_queue.put({"type": "text", "data": json.dumps({"type": "start"})})
        await receive_queue.put({"type": "binary", "data": b"\x00\x01\x02\x03" * 100})
        await receive_queue.put({"type": "text", "data": json.dumps({"type": "speech_end"})})

        mock_asr = AsyncMock()
        mock_asr.transcribe_pcm = AsyncMock(return_value="你好，今天天气怎么样？")

        mock_tts = AsyncMock()

        async def _mock_tts_stream(text, *, sample_rate=16000):
            async for c in _fake_tts_chunks(text, sample_rate=sample_rate):
                yield c

        mock_tts.synthesize_pcm_stream = _mock_tts_stream

        with patch("voice_layer.providers.realtime.cloud_realtime.ASRClient", return_value=mock_asr), \
             patch("voice_layer.providers.realtime.cloud_realtime.TTSClient", return_value=mock_tts), \
             patch("voice_layer.providers.realtime.cloud_realtime._stream_llm") as mock_llm, \
             patch(
                 "voice_layer.realtime_memory_sync.schedule_realtime_turn_memory_sync",
                 side_effect=_capture_sync,
             ) as mock_sched:

            mock_llm.side_effect = _fake_llm_stream

            provider = CloudRealtimeProvider()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    provider.run(
                        ws_send_json=_send_json,
                        ws_send_bytes=_send_bytes,
                        ws_receive=_receive,
                        memory_user_id="user_x",
                        memory_session_id="sess_y",
                    ),
                    timeout=3.0,
                )

        mock_sched.assert_called_once()
        assert len(sync_calls) == 1
        assert "你好" in sync_calls[0][0]
        assert sync_calls[0][1], "assistant_message should be non-empty"

    @pytest.mark.asyncio
    async def test_interrupt_clears_buffer(self):
        interrupted_seen = False

        async def _send_json(data: dict):
            nonlocal interrupted_seen
            if data.get("type") == "interrupted":
                interrupted_seen = True

        async def _send_bytes(data: bytes):
            pass

        receive_queue: asyncio.Queue = asyncio.Queue()

        async def _receive():
            return await receive_queue.get()

        await receive_queue.put({"type": "text", "data": json.dumps({"type": "start"})})
        await receive_queue.put({"type": "binary", "data": b"\x00\x01" * 50})
        await receive_queue.put({"type": "text", "data": json.dumps({"type": "interrupt"})})
        await receive_queue.put({"type": "disconnect"})

        provider = CloudRealtimeProvider()
        await provider.run(
            ws_send_json=_send_json,
            ws_send_bytes=_send_bytes,
            ws_receive=_receive,
        )

        assert interrupted_seen, "Should receive interrupted event"

    @pytest.mark.asyncio
    async def test_empty_speech_produces_empty_transcript(self):
        empty_transcript_seen = False

        receive_queue: asyncio.Queue = asyncio.Queue()

        async def _send_json(data: dict):
            nonlocal empty_transcript_seen
            if data.get("type") == "user_transcript_final" and data.get("text") == "" and not empty_transcript_seen:
                empty_transcript_seen = True
                receive_queue.put_nowait({"type": "disconnect"})

        async def _send_bytes(data: bytes):
            pass

        async def _receive():
            return await receive_queue.get()

        await receive_queue.put({"type": "text", "data": json.dumps({"type": "start"})})
        await receive_queue.put({"type": "binary", "data": b"\x00\x01" * 10})
        await receive_queue.put({"type": "text", "data": json.dumps({"type": "speech_end"})})

        mock_asr = AsyncMock()
        mock_asr.transcribe_pcm = AsyncMock(return_value="")

        mock_tts = AsyncMock()

        with patch("voice_layer.providers.realtime.cloud_realtime.ASRClient", return_value=mock_asr), \
             patch("voice_layer.providers.realtime.cloud_realtime.TTSClient", return_value=mock_tts):
            provider = CloudRealtimeProvider()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    provider.run(
                        ws_send_json=_send_json,
                        ws_send_bytes=_send_bytes,
                        ws_receive=_receive,
                    ),
                    timeout=3.0,
                )

        assert empty_transcript_seen, "Should receive empty user_transcript_final"

    @pytest.mark.asyncio
    async def test_ping_pong(self):
        pong_seen = False

        async def _send_json(data: dict):
            nonlocal pong_seen
            if data.get("type") == "pong":
                pong_seen = True

        async def _send_bytes(data: bytes):
            pass

        receive_queue: asyncio.Queue = asyncio.Queue()

        async def _receive():
            return await receive_queue.get()

        await receive_queue.put({"type": "text", "data": json.dumps({"type": "start"})})
        await receive_queue.put({"type": "text", "data": json.dumps({"type": "ping"})})
        await receive_queue.put({"type": "disconnect"})

        provider = CloudRealtimeProvider()
        await provider.run(
            ws_send_json=_send_json,
            ws_send_bytes=_send_bytes,
            ws_receive=_receive,
        )

        assert pong_seen, "Should respond to ping with pong"

    @pytest.mark.asyncio
    async def test_reset_clears_history(self):
        ready_count = 0

        async def _send_json(data: dict):
            nonlocal ready_count
            if data.get("type") == "ready":
                ready_count += 1

        async def _send_bytes(data: bytes):
            pass

        receive_queue: asyncio.Queue = asyncio.Queue()

        async def _receive():
            return await receive_queue.get()

        await receive_queue.put({"type": "text", "data": json.dumps({"type": "start"})})
        await receive_queue.put({"type": "text", "data": json.dumps({"type": "reset"})})
        await receive_queue.put({"type": "disconnect"})

        provider = CloudRealtimeProvider()
        await provider.run(
            ws_send_json=_send_json,
            ws_send_bytes=_send_bytes,
            ws_receive=_receive,
        )

        assert ready_count >= 2, f"Should receive ready after start AND after reset, got {ready_count}"

    @pytest.mark.asyncio
    async def test_error_on_llm_http_error(self):
        error_seen = False

        receive_queue: asyncio.Queue = asyncio.Queue()

        async def _send_json(data: dict):
            nonlocal error_seen
            if data.get("type") == "error" and not error_seen:
                error_seen = True
                receive_queue.put_nowait({"type": "disconnect"})

        async def _send_bytes(data: bytes):
            pass

        async def _receive():
            return await receive_queue.get()

        await receive_queue.put({"type": "text", "data": json.dumps({"type": "start"})})
        await receive_queue.put({"type": "binary", "data": b"\x00\x01" * 50})
        await receive_queue.put({"type": "text", "data": json.dumps({"type": "speech_end"})})

        mock_asr = AsyncMock()
        mock_asr.transcribe_pcm = AsyncMock(return_value="你好")

        mock_tts = AsyncMock()

        with patch("voice_layer.providers.realtime.cloud_realtime.ASRClient", return_value=mock_asr), \
             patch("voice_layer.providers.realtime.cloud_realtime.TTSClient", return_value=mock_tts), \
             patch("voice_layer.providers.realtime.cloud_realtime._stream_llm") as mock_llm:

            mock_llm.side_effect = RuntimeError("LLM HTTP 500: internal error")

            provider = CloudRealtimeProvider()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    provider.run(
                        ws_send_json=_send_json,
                        ws_send_bytes=_send_bytes,
                        ws_receive=_receive,
                    ),
                    timeout=3.0,
                )

        assert error_seen, "Should send error event on LLM failure"


class TestRealtimeStatus:
    def test_status_includes_cloud_provider(self):
        from voice_layer.providers.realtime import (
            get_realtime_status,
            init_registry,
            list_providers,
        )

        with patch("voice_layer.providers.realtime._providers", {}), \
             patch("voice_layer.providers.realtime._default_provider_name", "local"), \
             patch("shared_runtime.config.get_settings") as mock_settings, \
             patch("voice_layer.providers.realtime._can_use_cloud") as mock_can:

            mock_settings.return_value = MagicMock(
                realtime_voice_provider="",
                volc_app_id=None,
                volc_access_token=None,
            )
            mock_can.return_value = False

            init_registry()
            providers = list_providers()
            assert "local" in providers
            assert "cloud" in providers

            status = get_realtime_status()
            assert status["current_provider"] == "cloud"
            assert status["fallback_reason"] == "missing_voice_credentials"

    def test_status_cloud_auto_selects_when_credentials_present(self):
        from voice_layer.providers.realtime import (
            get_realtime_status,
            init_registry,
        )

        with patch("voice_layer.providers.realtime._providers", {}), \
             patch("voice_layer.providers.realtime._default_provider_name", "local"), \
             patch("shared_runtime.config.get_settings") as mock_settings, \
             patch("voice_layer.providers.realtime._can_use_cloud") as mock_can:

            mock_settings.return_value = MagicMock(
                realtime_voice_provider="",
                volc_app_id=None,
                volc_access_token=None,
            )
            mock_can.return_value = True

            init_registry()
            status = get_realtime_status()
            assert status["current_provider"] == "cloud"

    def test_status_cloud_with_explicit_env(self):
        from voice_layer.providers.realtime import (
            get_realtime_status,
            init_registry,
        )

        with patch("voice_layer.providers.realtime._providers", {}), \
             patch("voice_layer.providers.realtime._default_provider_name", "local"), \
             patch("shared_runtime.config.get_settings") as mock_settings, \
             patch("voice_layer.providers.realtime._can_use_cloud") as mock_can:

            mock_settings.return_value = MagicMock(
                realtime_voice_provider="cloud",
                volc_app_id=None,
                volc_access_token=None,
            )
            mock_can.return_value = True

            init_registry()
            status = get_realtime_status()
            assert status["current_provider"] == "cloud"
            assert status["configured_provider"] == "cloud"
            assert status["fallback_reason"] is None

    def test_status_cloud_fallback_when_no_credentials(self):
        from voice_layer.providers.realtime import (
            get_realtime_status,
            init_registry,
        )

        with patch("voice_layer.providers.realtime._providers", {}), \
             patch("voice_layer.providers.realtime._default_provider_name", "local"), \
             patch("shared_runtime.config.get_settings") as mock_settings, \
             patch("voice_layer.providers.realtime._can_use_cloud") as mock_can:

            mock_settings.return_value = MagicMock(
                realtime_voice_provider="cloud",
                volc_app_id=None,
                volc_access_token=None,
            )
            mock_can.return_value = False

            init_registry()
            status = get_realtime_status()
            assert status["current_provider"] == "cloud"
            assert status["configured_provider"] == "cloud"
            assert status["fallback_reason"] == "missing_voice_credentials"

    def test_cloud_credentials_accept_xiaomi_mimo_tts(self):
        from voice_layer.providers.realtime import _can_use_cloud

        with patch("shared_runtime.voice_runtime_config.get_runtime_voice_config") as mock_rt:
            mock_rt.return_value = {
                "asr_api_key": "asr-key",
                "tts_api_key": "tts-key",
                "tts_provider": " xiaomi_mimo ",
            }

            assert _can_use_cloud() is True
