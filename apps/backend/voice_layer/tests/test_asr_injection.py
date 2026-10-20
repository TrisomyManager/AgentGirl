import asyncio
import io
import json
import wave
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from shared_contracts.audio_transport import decode_audio_frame, encode_audio_frame
from shared_contracts.models import VoiceTranscriptionResult
from shared_contracts.protocols import SpeechRecognizer
from voice_layer.main import create_app
from voice_layer.providers.realtime.cloud_realtime import CloudRealtimeProvider


def test_upload_duration_uses_samples_instead_of_encoded_file_size():
    from voice_layer.asr import ASRClient

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b"\x00" * 192000)
    assert ASRClient._uploaded_duration_ms(buffer.getvalue()) == 1000
    assert ASRClient._uploaded_duration_ms(buffer.getvalue()[:96044]) == 500
    assert ASRClient._uploaded_duration_ms(b"ID3" + b"\x00" * 96000) == 0


class Recognizer:
    def __init__(self, name, calls):
        self.name, self.calls = name, calls
        self.closed = 0

    async def transcribe(self, audio_data, language="zh-CN", model=None, **kwargs):
        self.calls.append((self.name, audio_data, language, kwargs))
        return VoiceTranscriptionResult(text=self.name, confidence=0.42, language=language, duration_ms=345)

    async def transcribe_pcm(self, pcm_int16, sample_rate=16000):
        self.calls.append((self.name, pcm_int16, sample_rate))
        return "我需要休息。"

    async def close(self):
        self.closed += 1


async def test_factories_are_app_scoped_and_preserve_host_metadata(monkeypatch):
    calls, clients = [], []

    def factory(name):
        def create():
            recognizer = Recognizer(name, calls)
            clients.append(recognizer)
            return recognizer

        return create

    monkeypatch.setattr("voice_layer.asr.ASRClient", lambda: pytest.fail("Default provider must not be constructed"))
    first, second = create_app(asr_factory=factory("first")), create_app(asr_factory=factory("second"))
    for app, name in ((first, "first"), (second, "second"), (first, "first")):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://asr") as client:
            result = await client.post(
                "/voice/transcribe",
                files={"audio": ("sample.webm", b"encoded", "audio/webm")},
                data={"language": "ja-JP"},
            )
        assert result.status_code == 200
        data = result.json()
        assert (data["text"], data["confidence"], data["duration_ms"]) == (name, 0.42, 345)
    assert [item[0] for item in calls] == ["first", "second", "first"]
    assert all(item[1:3] == (b"encoded", "ja-JP") for item in calls)
    assert calls[0][3] == {"upload_filename": "sample.webm", "upload_content_type": "audio/webm"}
    assert all(isinstance(item, SpeechRecognizer) and item.closed == 1 for item in clients)


async def test_request_failure_and_repeated_cancellation_close_owned_service():
    started, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Pending(Recognizer):
        async def transcribe(self, *args, **kwargs):
            started.set()
            await asyncio.Event().wait()

        async def close(self):
            closing.set()
            await release.wait()
            await super().close()

    recognizer = Pending("pending", [])
    app = create_app(asr_factory=lambda: recognizer)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://asr") as client:
        task = asyncio.create_task(client.post("/voice/transcribe", files={"audio": ("sample", b"test")}))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        await asyncio.wait_for(closing.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert recognizer.closed == 1

    class Broken(Recognizer):
        async def transcribe(self, *args, **kwargs):
            raise RuntimeError("synthetic-private-asr-error")

    broken = Broken("broken", [])
    app = create_app(asr_factory=lambda: broken)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://asr"
    ) as client:
        response = await client.post("/voice/transcribe", files={"audio": ("sample", b"test")})
    assert response.status_code == 500 and "synthetic-private" not in response.text
    assert broken.closed == 1


def test_cloud_websocket_uses_app_injected_pcm_recognizer(monkeypatch):
    from voice_layer import realtime
    from voice_layer.providers.realtime import cloud_realtime

    calls, clients = [], []

    def factory():
        item = Recognizer("cloud-host", calls)
        clients.append(item)
        return item

    class Speech:
        provider = "fixture"

        async def synthesize_pcm_stream(self, text, **kwargs):
            yield b"\x01\x00" * 1600

        async def close(self):
            pass

    async def tokens(*args, **kwargs):
        yield "可以，先休息一下。"

    monkeypatch.setattr(realtime, "is_registry_initialized", lambda: True)
    monkeypatch.setattr(realtime, "get_provider", CloudRealtimeProvider)
    monkeypatch.setattr(cloud_realtime, "ASRClient", lambda: pytest.fail("Default ASR must not be called"))
    monkeypatch.setattr(cloud_realtime, "TTSClient", Speech)
    monkeypatch.setattr(cloud_realtime, "_stream_llm", tokens)
    monkeypatch.setattr(cloud_realtime, "load_conversation_context", AsyncMock(return_value=None))
    monkeypatch.setattr("voice_layer.realtime_memory_sync.schedule_realtime_turn_memory_sync", lambda **kwargs: None)
    app = create_app(asr_factory=factory)
    pcm = b"\x00\x01" * 2048
    with TestClient(app) as client, client.websocket_connect("/voice/realtime?audio_protocol=framed-v1") as ws:
        assert ws.receive_json()["type"] == "transport_ready"
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(encode_audio_frame(pcm, stream_id=0, sequence=0))
        ws.send_json({"type": "speech_end"})
        events, audio = [], []
        while True:
            response = ws.receive()
            if response.get("bytes"):
                audio.append(decode_audio_frame(response["bytes"]).payload)
            else:
                event = json.loads(response["text"])
                events.append(event)
                if event["type"] == "turn_done":
                    break
        assert any(event.get("text") == "我需要休息。" for event in events)
        received = b"".join(audio)
        assert len(received) >= 3200 and received == b"\x01\x00" * (len(received) // 2)
    assert calls == [("cloud-host", pcm, 16000)]
    assert len(clients) == 1 and clients[0].closed == 1
