"""Exercise SAUC framing, audio conversion and failure handling over real sockets."""

import gzip
import io
import json
import struct
import wave

import httpx
import pytest
from websockets.asyncio.server import serve

from voice_layer.providers.volcengine import _asr_response, transcribe


def recording():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x01\x00\x02\x00" * 3200)
    return buf.getvalue()


def response(data, *, final=False):
    body = gzip.compress(json.dumps(data).encode())
    return (bytes([0x11, 0x93 if final else 0x91, 0x11, 0])
            + struct.pack(">iI", -2 if final else 1, len(body)) + body)


@pytest.mark.parametrize("failure", [None, "vendor", "closed"])
async def test_sauc_normalizes_audio_and_requires_final_result(failure):
    frames = []

    async def vendor(ws):
        assert ws.request.path == "/api/v3/sauc/bigmodel_nostream"
        assert ws.request.headers["X-Api-Key"] == "test-key"
        assert ws.request.headers["X-Api-Resource-Id"] == "volc.seedasr.sauc.duration"
        config = await ws.recv()
        assert config[:4] == b"\x11\x10\x11\x00"
        request = json.loads(gzip.decompress(config[8:]))
        assert request["audio"] == {"format": "pcm", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1}
        await ws.send(response({}))
        async for frame in ws:
            assert struct.unpack(">I", frame[4:8])[0] == len(frame[8:])
            assert frame[:4] in (b"\x11\x20\x01\x00", b"\x11\x22\x01\x00")
            frames.append(gzip.decompress(frame[8:]))
            if frame[1] & 2:
                if failure == "closed":
                    return  # No final response must never be reported as success.
                if failure == "vendor":
                    body = b"permission denied"
                    await ws.send(b"\x11\xf0\x00\x00" + struct.pack(">II", 45000030, len(body)) + body)
                else:
                    await ws.send(response({"result": {"text": "识别成功。"}}, final=True))
                return
            await ws.send(response({"result": {"text": "临时结果"}}))

    async with serve(vendor, "127.0.0.1", 0) as server:
        base = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        async with httpx.AsyncClient() as client:
            kwargs = {"api_key": "test-key", "base_url": base, "resource_id": "volc.seedasr.sauc.duration"}
            if failure:
                with pytest.raises(RuntimeError, match="45000030" if failure == "vendor" else "提前结束"):
                    await transcribe(client, recording(), **kwargs)
            else:
                assert await transcribe(client, recording(), **kwargs) == ("识别成功。", 1.0)
    assert len(frames) == 2
    assert 12790 <= sum(map(len, frames)) <= 12800  # 400ms at 16kHz, mono int16


@pytest.mark.parametrize("frame", [b"short", response({})[:-1], b"\x11\x91\x11\x00"])
def test_sauc_rejects_truncated_frames(frame):
    with pytest.raises(RuntimeError, match="响应"):
        _asr_response(frame)
