"""Doubao Speech v3 adapters (API Key authentication)."""

import asyncio
import base64
import contextlib
import gzip
import io
import json
import struct
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import httpx
from websockets.asyncio.client import connect


def _asr_frame(payload: bytes, *, audio: bool = False, last: bool = False) -> bytes:
    body = gzip.compress(payload)
    header = bytes([0x11, (0x20 if audio else 0x10) | (2 if last else 0),
                    0x01 if audio else 0x11, 0])
    return header + struct.pack(">I", len(body)) + body


def _asr_response(frame: bytes) -> tuple[dict, bool]:
    """Read SAUC response sequence/error fields before the payload length."""
    if len(frame) < 8:
        raise RuntimeError("火山语音识别响应不完整")
    kind, flags = frame[1] >> 4, frame[1] & 15
    offset = (frame[0] & 15) * 4
    error = 0
    try:
        if offset < 4 or kind not in (9, 15):
            raise ValueError("unexpected header")
        if kind == 15:
            error = struct.unpack_from(">I", frame, offset)[0]
            offset += 4
        elif flags & 1:
            offset += 4  # optional signed sequence, including final negative sequence
        size = struct.unpack_from(">I", frame, offset)[0]
        payload = frame[offset + 4:]
        if len(payload) != size:
            raise ValueError("truncated payload")
        if frame[2] & 15 == 1:
            payload = gzip.decompress(payload)
        if error:
            raise RuntimeError(f"火山语音识别失败 ({error}): {payload.decode('utf-8', errors='replace')}")
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("unexpected response")
    except (ValueError, OSError, EOFError, struct.error) as exc:
        raise RuntimeError("火山语音识别响应格式错误") from exc
    return data, bool(flags & 2)


async def transcribe_streaming(
    audio: bytes, *, api_key: str, base_url: str, resource_id: str,
) -> tuple[str, float]:
    """Recognize a recording with the already-enabled streaming ASR 2.0 service.

    The nostream endpoint returns a complete sentence after the final audio
    frame; it doesn't require public file hosting or file-recognition grants.
    """
    from pydub import AudioSegment

    from voice_layer import audio_utils  # noqa: F401 - configures bundled ffmpeg

    def decode() -> bytes:
        segment = AudioSegment.from_file(io.BytesIO(audio))
        return segment.set_frame_rate(16000).set_channels(1).set_sample_width(2).raw_data

    pcm = await asyncio.to_thread(decode)
    if not pcm:
        raise RuntimeError("音频内容为空")
    parts = urlsplit(base_url)
    endpoint = urlunsplit(("wss" if parts.scheme in ("https", "wss") else "ws",
                          parts.netloc, "/api/v3/sauc/bigmodel_nostream", "", ""))
    request = {
        "user": {"uid": "companion"},
        "audio": {"format": "pcm", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
        "request": {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True,
                    "result_type": "full"},
    }
    async with asyncio.timeout(max(60, len(pcm) / 32000 + 30)):
        async with connect(endpoint, additional_headers={
            "X-Api-Key": api_key, "X-Api-Resource-Id": resource_id,
            "X-Api-Connect-Id": str(uuid.uuid4()), "X-Api-Request-Id": str(uuid.uuid4()),
        }, open_timeout=15, close_timeout=5, max_size=4 * 1024 * 1024) as ws:
            await ws.send(_asr_frame(json.dumps(request).encode()))

            async def send_audio() -> None:
                for start in range(0, len(pcm), 6400):  # 200ms of mono int16 PCM
                    chunk = pcm[start:start + 6400]
                    await ws.send(_asr_frame(chunk, audio=True, last=start + 6400 >= len(pcm)))
                    if start + 6400 < len(pcm):
                        await asyncio.sleep(0.2)

            sender = asyncio.create_task(send_audio())
            text = ""
            try:
                async for frame in ws:
                    if not isinstance(frame, bytes):
                        raise RuntimeError("火山语音识别返回非二进制响应")
                    data, final = _asr_response(frame)
                    code = data.get("code", 20000000)
                    if code not in (0, 20000000):
                        raise RuntimeError(f"火山语音识别失败 ({code}): {data.get('message', '')}")
                    result = data.get("result") or {}
                    if "text" in result:
                        text = result["text"].strip()
                    if final:
                        await sender
                        return text, 1.0 if text else 0.0
                raise RuntimeError("火山语音识别连接提前结束，请重试。")
            finally:
                sender.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sender


async def transcribe(
    client: httpx.AsyncClient, audio: bytes, *, api_key: str, base_url: str, resource_id: str,
) -> tuple[str, float]:
    if resource_id in {"volc.seedasr.sauc.duration", "volc.seedasr.sauc.concurrent",
                       "volc.bigasr.sauc.duration", "volc.bigasr.sauc.concurrent"}:
        return await transcribe_streaming(audio, api_key=api_key, base_url=base_url, resource_id=resource_id)
    response = await client.post(
        f"{base_url}/api/v3/auc/bigmodel/recognize/flash",
        headers={
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
        },
        json={
            "user": {"uid": "companion"},
            "audio": {"data": base64.b64encode(audio).decode("ascii")},
            "request": {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True},
        },
    )
    response.raise_for_status()
    code = response.headers.get("X-Api-Status-Code")
    if code == "20000003":  # Silence is a successful empty transcription.
        return "", 0.0
    if code != "20000000":
        raise RuntimeError(f"火山语音识别失败 ({code}): {response.headers.get('X-Api-Message', '')}")
    return response.json().get("result", {}).get("text", "").strip(), 1.0


async def synthesize_stream(
    client: httpx.AsyncClient, text: str, *, api_key: str, base_url: str,
    resource_id: str, speaker: str, fmt: str = "mp3", sample_rate: int = 24000, speed: float = 1.0,
) -> AsyncIterator[bytes]:
    completed = False
    async with client.stream(
        "POST", f"{base_url}/api/v3/tts/unidirectional",
        headers={
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
        },
        json={
            "user": {"uid": "companion"},
            "req_params": {
                "text": text, "speaker": speaker,
                "audio_params": {
                    "format": fmt, "sample_rate": sample_rate,
                    "speech_rate": max(-50, min(100, round((speed - 1.0) * 100))),
                },
            },
        },
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            event = json.loads(line)
            code = event.get("code")
            if code == 20000000:
                completed = True
                break
            if code != 0:
                raise RuntimeError(f"火山语音合成失败 ({code}): {event.get('message', '')}")
            if event.get("data"):
                yield base64.b64decode(event["data"], validate=True)
    if not completed:
        raise RuntimeError("火山语音合成连接提前结束，请重试。")
