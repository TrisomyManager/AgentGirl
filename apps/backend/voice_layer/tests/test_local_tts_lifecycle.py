import asyncio
import threading

import pytest

from voice_layer import local_tts


async def test_local_tts_cancellation_stops_bounded_producer_and_closes_its_iterator(monkeypatch):
    produced = []
    closed = threading.Event()

    def source(text):
        try:
            for index in range(10000):
                produced.append(index)
                yield b"\x00\x00"
        finally:
            closed.set()

    monkeypatch.setattr(local_tts, "synthesize_pcm_chunks_sync", source)
    chunks = local_tts.synthesize_pcm_chunks("合成验收")
    assert await anext(chunks) == b"\x00\x00"
    await chunks.aclose()
    assert closed.is_set() and len(produced) <= 11


async def test_local_tts_normal_completion_keeps_chunk_order(monkeypatch):

    # A real synchronous generator, like Piper's public adapter.
    def source(text):
        yield from [b"12", b"34", b"56"]

    monkeypatch.setattr(local_tts, "synthesize_pcm_chunks_sync", source)
    assert [chunk async for chunk in local_tts.synthesize_pcm_chunks("test")] == [b"12", b"34", b"56"]


async def test_local_tts_errors_cross_the_bridge_without_abandoned_queue_waiters(monkeypatch):
    def source(text):
        raise RuntimeError("synthetic engine failure")
        yield b""

    monkeypatch.setattr(local_tts, "synthesize_pcm_chunks_sync", source)
    with pytest.raises(RuntimeError, match="本地语音"):
        async for _ in local_tts.synthesize_pcm_chunks("test"):
            pass


async def test_cancelling_a_request_waiting_for_the_engine_never_starts_its_synthesis(monkeypatch):
    calls = []

    def source(text):
        calls.append(text)
        yield b"12"

    monkeypatch.setattr(local_tts, "synthesize_pcm_chunks_sync", source)
    local_tts._synthesis_lock.acquire()
    try:

        async def consume():
            async for _ in local_tts.synthesize_pcm_chunks("cancelled"):
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not calls
    finally:
        local_tts._synthesis_lock.release()
