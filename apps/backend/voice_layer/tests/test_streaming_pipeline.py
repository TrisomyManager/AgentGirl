import asyncio
import json

import pytest

from voice_layer.streaming_pipeline import stream_pcm_speech, stream_speech


@pytest.mark.parametrize("provider", ["cloud", "local"])
async def test_realtime_input_overflow_is_bounded_and_reset_accepts_new_audio(provider, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from voice_layer.providers.realtime import cloud_realtime, local_realtime

    events = []
    if provider == "cloud":
        monkeypatch.setattr(cloud_realtime, "ASRClient", lambda: SimpleNamespace(
            provider="test", default_model="test", close=AsyncMock()))
        monkeypatch.setattr(cloud_realtime, "TTSClient", lambda: SimpleNamespace(
            provider="test", close=AsyncMock()))
        session_class = cloud_realtime._CloudSession
    else:
        monkeypatch.setattr(local_realtime.local_asr, "warmup", lambda: None)
        monkeypatch.setattr(local_realtime.local_tts, "warmup", lambda: None)
        session_class = local_realtime._LocalSession
    session = session_class(AsyncMock(side_effect=events.append), AsyncMock())
    messages = iter([
        {"type": "binary", "data": b"\0" * (16000 * 2 * 60 + 1)},
        {"type": "binary", "data": b"ignored"},
        {"type": "text", "data": json.dumps({"type": "reset"})},
        {"type": "binary", "data": b"\0\0"},
        {"type": "disconnect"},
    ])

    async def receive():
        return next(messages)

    await session.run(receive)
    assert session._pcm_buffer == b"\0\0" and not session._audio_overflow
    assert [event["code"] for event in events if event["type"] == "error"] == ["audio_too_long"]
    assert next(event for event in events if event["type"] == "error")["recoverable"] is True


async def test_real_tts_wrapper_closes_the_provider_stream_before_returning(monkeypatch):
    from voice_layer.providers import volcengine
    from voice_layer.tts import TTSClient

    closed = asyncio.Event()

    async def synthesize(*args, **kwargs):
        try:
            yield b"\x00\x00"
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(volcengine, "synthesize_stream", synthesize)
    tts = TTSClient()
    tts.provider = "volcengine"
    tts.api_key = "synthetic-test-key"
    stream = tts.synthesize_pcm_stream("合成验收")
    try:
        assert await anext(stream) == b"\x00\x00"
        await stream.aclose()
        assert closed.is_set()
    finally:
        await tts.close()


async def test_pcm_prefetch_synthesizes_out_of_order_but_never_interleaves_audio():
    second_started = asyncio.Event()
    order = []

    async def tokens():
        yield "第一句。第二句。"

    async def synthesize(text):
        if text.startswith("第一"):
            await asyncio.wait_for(second_started.wait(), 1)
        else:
            second_started.set()
        yield text.encode("utf-8")

    async def delta(text):
        pass

    async def start(text, index):
        order.append(("start", index))

    async def audio(chunk):
        order.append(("audio", chunk.decode("utf-8")))

    async def done(index):
        order.append(("done", index))

    await stream_pcm_speech(
        tokens(), synthesize=synthesize, on_delta=delta, on_start=start, on_audio=audio, on_done=done
    )
    assert order == [("start", 0), ("audio", "第一句。"), ("done", 0), ("start", 1), ("audio", "第二句。"), ("done", 1)]


@pytest.mark.parametrize("provider", ["cloud", "local"])
async def test_real_session_uses_parallel_generation_and_interrupt_waits_for_output_cleanup(provider, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from voice_layer.providers.realtime import cloud_realtime, local_realtime

    module = cloud_realtime if provider == "cloud" else local_realtime
    session_class = module._CloudSession if provider == "cloud" else module._LocalSession
    asr = AsyncMock(return_value="合成验收")
    speak_started, next_token = asyncio.Event(), asyncio.Event()
    cleanup = asyncio.Event()
    events, audio = [], []

    async def send_json(value):
        events.append(value)
        if value.get("type") == "assistant_text_delta" and value.get("text") == "第二句。":
            next_token.set()

    async def send_bytes(value):
        audio.append(value)

    async def synthesize(sentence, **kwargs):
        speak_started.set()
        try:
            await next_token.wait()
            yield b"\x00\x00"
            await asyncio.Event().wait()
        finally:
            cleanup.set()

    async def tokens(*args):
        yield "第一句。"
        await speak_started.wait()
        yield "第二句。"

    monkeypatch.setattr(module, "_stream_llm", tokens)
    scheduled = Mock()
    monkeypatch.setattr("voice_layer.realtime_memory_sync.schedule_realtime_turn_memory_sync", scheduled)
    session = session_class(send_json, send_bytes, memory_user_id="isolated", memory_session_id="session")
    if provider == "cloud":
        session._asr = SimpleNamespace(transcribe_pcm=asr)
        session._tts = SimpleNamespace(synthesize_pcm_stream=synthesize)
    else:
        monkeypatch.setattr(local_realtime.local_asr, "transcribe_pcm", asr)
        monkeypatch.setattr(local_realtime.local_tts, "synthesize_pcm_chunks", synthesize)
    session._current_turn_task = asyncio.create_task(session._run_turn(b"\x00\x00"))
    await asyncio.wait_for(next_token.wait(), 1)
    await session._on_interrupt()
    assert cleanup.is_set() and events[-1]["type"] == "interrupted"
    assert session._current_turn_task is None
    assert not any(turn["role"] == "assistant" for turn in session._history)
    scheduled.assert_not_called()
    transmitted = len(audio)
    await asyncio.sleep(0)
    assert len(audio) == transmitted


async def test_llm_continues_while_first_sentence_is_being_synthesized_and_order_is_preserved():
    first_audio = asyncio.Event()
    second_delta = asyncio.Event()
    seen = []

    async def tokens():
        yield "第一句。"
        await first_audio.wait()
        yield "第二句。第三句。"
        second_delta.set()
        yield "尾句"

    async def delta(text):
        seen.append(("text", text))

    async def speak(sentence, index):
        if index == 0:
            first_audio.set()
            # The sequential implementation deadlocks here: LLM must progress
            # while TTS for the first sentence is still running.
            await asyncio.wait_for(second_delta.wait(), 1)
        seen.append(("speech", sentence))

    result = await stream_speech(tokens(), on_delta=delta, on_sentence=speak)
    assert result == "第一句。第二句。第三句。尾句"
    assert [text for kind, text in seen if kind == "speech"] == ["第一句。", "第二句。", "第三句。", "尾句"]


async def test_cancellation_waits_for_tts_cleanup_closes_llm_and_drops_queued_speech():
    entered, producer_closed, tts_closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    spoken = []

    async def tokens():
        try:
            for _ in range(50):
                yield "一句话。"
        finally:
            producer_closed.set()

    async def delta(text):
        pass

    async def speak(sentence, index):
        spoken.append(index)
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            tts_closed.set()

    worker = asyncio.create_task(stream_speech(tokens(), on_delta=delta, on_sentence=speak, queue_size=2))
    await entered.wait()
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker
    assert producer_closed.is_set() and tts_closed.is_set() and spoken == [0]


async def test_backpressure_limits_generation_when_tts_is_slow():
    entered, generated = asyncio.Event(), []

    async def tokens():
        for index in range(1000):
            generated.append(index)
            yield "一句话。"

    async def delta(text):
        pass

    async def speak(sentence, index):
        entered.set()
        await asyncio.Event().wait()

    worker = asyncio.create_task(stream_speech(tokens(), on_delta=delta, on_sentence=speak, queue_size=2))
    await entered.wait()
    for _ in range(5):
        await asyncio.sleep(0)
    assert len(generated) <= 4
    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)


async def test_consumer_failure_cancels_and_closes_the_blocked_producer():
    closed = asyncio.Event()

    async def tokens():
        try:
            yield "第一句。"
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def delta(text):
        pass

    async def speak(sentence, index):
        raise OSError("synthetic transport closed")

    with pytest.raises(ExceptionGroup):
        await stream_speech(tokens(), on_delta=delta, on_sentence=speak)
    assert closed.is_set()


async def test_tts_timeout_is_bounded_and_never_advances_to_the_next_sentence():
    calls = []

    async def tokens():
        yield "第一句。第二句。"

    async def delta(text):
        pass

    async def speak(sentence, index):
        calls.append(index)
        await asyncio.Event().wait()

    with pytest.raises(ExceptionGroup):
        await stream_speech(tokens(), on_delta=delta, on_sentence=speak, sentence_timeout=0.02)
    assert calls == [0]


async def test_total_deadline_handles_a_silent_llm():
    async def tokens():
        await asyncio.Event().wait()
        yield ""

    async def delta(text):
        pass

    async def speak(sentence, index):
        pass

    with pytest.raises(TimeoutError):
        await stream_speech(tokens(), on_delta=delta, on_sentence=speak, deadline_seconds=0.02)
