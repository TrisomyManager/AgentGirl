"""Local realtime provider — memory sync hook."""

from __future__ import annotations

import asyncio
import contextlib
import json
from unittest.mock import AsyncMock, patch

import pytest

from voice_layer.providers.realtime.local_realtime import LocalRealtimeProvider


async def _fake_llm_stream(_history):
    for c in "今天天气不错。":
        yield c


async def _fake_pcm_chunks(_sentence: str):
    yield b"\x00\x01"


@pytest.mark.asyncio
async def test_local_turn_schedules_memory_sync():
    receive_queue: asyncio.Queue = asyncio.Queue()
    sync_called = False

    async def _send_json(data: dict):
        del data

    async def _send_bytes(data: bytes):
        pass

    async def _receive():
        return await receive_queue.get()

    await receive_queue.put({"type": "text", "data": json.dumps({"type": "start"})})
    await receive_queue.put({"type": "binary", "data": b"\x00\x01" * 200})
    await receive_queue.put({"type": "text", "data": json.dumps({"type": "speech_end"})})

    def _mark_sync(**_kwargs):
        nonlocal sync_called
        sync_called = True
        receive_queue.put_nowait({"type": "disconnect"})

    with patch("voice_layer.local_asr.transcribe_pcm", new_callable=AsyncMock, return_value="测试一句"), \
         patch("voice_layer.local_asr.warmup"), \
         patch("voice_layer.local_tts.warmup"), \
         patch(
             "voice_layer.local_tts.synthesize_pcm_chunks",
             side_effect=_fake_pcm_chunks,
         ), \
         patch("voice_layer.providers.realtime.local_realtime._stream_llm", side_effect=_fake_llm_stream), \
         patch("voice_layer.realtime_memory_sync.schedule_realtime_turn_memory_sync", side_effect=_mark_sync):

        provider = LocalRealtimeProvider()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(
                provider.run(
                    ws_send_json=_send_json,
                    ws_send_bytes=_send_bytes,
                    ws_receive=_receive,
                    memory_user_id="u_loc",
                    memory_session_id="s_loc",
                ),
                timeout=3.0,
            )

    assert sync_called, "memory sync should be scheduled after a full turn"
