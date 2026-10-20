import asyncio
import json

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from shared_contracts.audio_transport import AudioFrameError, decode_audio_frame, encode_audio_frame


def test_cross_language_frame_fixture_and_invalid_packets():
    data = encode_audio_frame(bytes([0, 128, 255, 127]), stream_id=0x01020304, sequence=5)
    assert list(data) == [67, 78, 65, 86, 1, 1, 0, 0, 1, 2, 3, 4, 0, 0, 0, 5, 0, 0, 0, 4, 0, 128, 255, 127]
    assert decode_audio_frame(data).stream_id == 0x01020304
    assert decode_audio_frame(data).payload == bytes([0, 128, 255, 127])
    for bad in (data[:20], data[:-1], data + b"x", data[:4] + b"\x02" + data[5:], b"x" * (2 * 1024 * 1024 + 21)):
        with pytest.raises(AudioFrameError):
            decode_audio_frame(bad)
    with pytest.raises(AudioFrameError):
        encode_audio_frame(b"abc", stream_id=1, sequence=0x100000000)


@pytest.fixture
def wire_app(monkeypatch):
    from voice_layer import realtime

    class Provider:
        provider_name = "fixture"

        async def run(self, ws_send_json, ws_send_bytes, ws_receive, **kwargs):
            await ws_send_json({"type": "ready"})
            await ws_send_json({"type": "assistant_sentence_start", "sample_rate": 24000, "audio_format": "pcm"})
            await ws_send_bytes(b"\x01\x00\x02\x00")
            while (message := await ws_receive())["type"] != "disconnect":
                if message["type"] == "binary":
                    await ws_send_json({"type": "echo_size", "bytes": len(message["data"])})

    monkeypatch.setattr(realtime, "get_provider", Provider)
    monkeypatch.setattr(realtime, "is_registry_initialized", lambda: True)
    app = FastAPI()

    @app.websocket("/realtime")
    async def socket(ws: WebSocket):
        await realtime.realtime_handler(ws)

    return app


@pytest.mark.parametrize("wire", ["", "?audio_protocol=framed-v1"])
def test_websocket_legacy_and_negotiated_frame_roundtrip(wire_app, wire):
    with TestClient(wire_app) as client, client.websocket_connect("/realtime" + wire) as ws:
        if wire:
            assert ws.receive_json()["audio_protocol"] == "framed-v1"
        assert ws.receive_json()["type"] == "ready"
        metadata = ws.receive_json()
        received = ws.receive_bytes()
        if wire:
            frame = decode_audio_frame(received)
            assert frame.sequence == 0 and frame.stream_id == metadata["audio_stream_id"] == 1
            received = frame.payload
            ws.send_bytes(encode_audio_frame(b"\x03\x00", stream_id=0, sequence=0))
        else:
            assert "audio_stream_id" not in metadata
            ws.send_bytes(b"\x03\x00")
        assert received == b"\x01\x00\x02\x00"
        assert ws.receive_json() == {"type": "echo_size", "bytes": 2}


def test_websocket_rejects_unknown_protocol_and_replayed_uplink(wire_app):
    with TestClient(wire_app) as client:
        with client.websocket_connect("/realtime?audio_protocol=unknown") as ws:
            with pytest.raises(WebSocketDisconnect) as error:
                ws.receive_json()
            assert error.value.code == 1002

        with client.websocket_connect("/realtime?audio_protocol=framed-v1") as ws:
            for _ in range(3):
                ws.receive_json()
            ws.receive_bytes()
            frame = encode_audio_frame(b"\x00\x00", stream_id=0, sequence=0)
            ws.send_bytes(frame)
            assert ws.receive_json()["bytes"] == 2
            ws.send_bytes(frame)
            with pytest.raises(WebSocketDisconnect) as error:
                ws.receive_json()
            assert error.value.code == 1002


async def test_cancelled_output_send_settles_before_next_sequence(monkeypatch):
    from voice_layer import realtime

    class Socket:
        query_params = {"audio_protocol": "framed-v1"}
        scope = {}

        def __init__(self):
            self.started, self.release = asyncio.Event(), asyncio.Event()
            self.packets, self.events = [], []

        async def accept(self):
            pass

        async def close(self, **kwargs):
            pass

        async def send_json(self, event):
            self.events.append(event)

        async def send_text(self, data):
            self.events.append(json.loads(data))

        async def send_bytes(self, data):
            if not self.packets:
                self.started.set()
                await self.release.wait()
            self.packets.append(data)

    socket = Socket()

    class Provider:
        provider_name = "fixture"

        async def run(self, ws_send_json, ws_send_bytes, **kwargs):
            await ws_send_json({"type": "assistant_sentence_start"})
            sending = asyncio.create_task(ws_send_bytes(b"\x00\x00"))
            await socket.started.wait()
            sending.cancel()
            await asyncio.sleep(0)
            sending.cancel()
            await asyncio.sleep(0)
            assert not sending.done()
            socket.release.set()
            with pytest.raises(asyncio.CancelledError):
                await sending
            await ws_send_json({"type": "interrupted"})
            await ws_send_bytes(b"ignored")
            await ws_send_json({"type": "assistant_sentence_start"})
            await ws_send_bytes(b"\x01\x00")

    monkeypatch.setattr(realtime, "get_provider", Provider)
    monkeypatch.setattr(realtime, "is_registry_initialized", lambda: True)
    await realtime.realtime_handler(socket)
    frames = [decode_audio_frame(packet) for packet in socket.packets]
    assert [(frame.stream_id, frame.sequence) for frame in frames] == [(1, 0), (2, 1)]


@pytest.mark.parametrize(
    "control,code",
    [
        ("[]", 1002),
        ('{"type":1}', 1002),
        (json.dumps({"type": "ping", "text": "汉" * 22000}, ensure_ascii=False), 1009),
    ],
    ids=["array-control", "numeric-control-type", "utf8-control-too-large"],
)
def test_websocket_control_shape_and_utf8_size_bounds(wire_app, control, code):
    with TestClient(wire_app) as client, client.websocket_connect("/realtime") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.receive_bytes()
        ws.send_text(control)
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == code
