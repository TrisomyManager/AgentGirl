import asyncio
from unittest.mock import AsyncMock

import pytest

from core_orchestrator.streaming_voice import stream_voice_events


async def test_sse_route_closes_the_host_iterator_when_the_client_disconnects(monkeypatch):
    from types import SimpleNamespace

    import core_orchestrator.api as api

    closed = asyncio.Event()

    async def stream(context):
        try:
            yield {"event": "meta"}
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(api, "get_orchestrator", AsyncMock(return_value=SimpleNamespace(process_turn_stream=stream)))
    response = await api.process_turn_stream(api.TurnRequest(session_id="s", user={"user_id": "u"}, user_message="hi"))
    await anext(response.body_iterator)
    await response.body_iterator.aclose()
    assert closed.is_set()


async def test_host_closes_inner_generation_and_releases_the_session_lock_on_disconnect(monkeypatch):
    import core_orchestrator.orchestrator as module
    from shared_contracts.models import TurnContext, UserProfile

    closed = asyncio.Event()

    async def stream(context):
        try:
            yield {"event": "meta"}
            await asyncio.Event().wait()
        finally:
            closed.set()

    host = module.Orchestrator()
    monkeypatch.setattr(host, "_record_user_activity", AsyncMock())
    monkeypatch.setattr(module, "stream_assistant_response", stream)
    tc = TurnContext(turn_id="t", session_id="s", user=UserProfile(user_id="u"), platform="app", user_message="hi")
    iterator = host.process_turn_stream(tc)
    await anext(iterator)
    await iterator.aclose()
    assert closed.is_set() and not host._turn_coordinator._entries


async def source_events(text="第一句话有八个字符。第二句话也有八个字符。"):
    yield {"event": "meta", "_voice_context": {"voice_id": "profile", "emotion": "happy"}}
    yield {"event": "token", "text": text}
    yield {"event": "done", "_state": {}}


async def test_concurrent_synthesis_is_delivered_in_order_and_summary_uses_actual_results():
    second_ready = asyncio.Event()
    finished = []

    async def synthesize(text, context):
        assert context["voice_id"] == "profile"
        if text.startswith("第一"):
            await asyncio.wait_for(second_ready.wait(), 1)
        else:
            second_ready.set()
        finished.append(text)
        return {"audio_url": "/audio/" + text, "duration_ms": 500}

    events = [event async for event in stream_voice_events(source_events(), synthesize, turn_id="t")]
    assert finished[0].startswith("第二")
    assert [event["seq"] for event in events if event["event"] == "voice_segment"] == [0, 1]
    assert "_voice_context" not in events[0]
    assert events[-2] == {
        "event": "voice_done",
        "turn_id": "t",
        "segments": 2,
        "successful_segments": 2,
        "total_duration_ms": 1000,
        "truncated": False,
    }
    assert events[-1]["_state"]["voice_mode"] == "segmented"
    assert len(events[-1]["_state"]["voice_segments"]) == 2
    for event in events:
        if event["event"] == "voice_segment":
            assert event["avatar_timeline"]["segment_seq"] == event["seq"]
            assert event["avatar_timeline"]["turn_id"] == "t"
            assert event["avatar_timeline"]["duration_ms"] == 500
            assert event["avatar_timeline"]["clock"] == "audio_playback"


async def test_first_voice_arrives_before_the_llm_finishes():
    delivered = asyncio.Event()

    async def source():
        yield {"event": "meta"}
        yield {"event": "token", "text": "第一句话有八个字符。"}
        await asyncio.wait_for(delivered.wait(), 1)
        yield {"event": "token", "text": "还没有结束的下一句。"}
        yield {"event": "done", "_state": {}}

    async def synthesize(*args):
        return {"audio_url": "/voice/first.mp3"}

    events = []
    async for event in stream_voice_events(source(), synthesize, turn_id="t"):
        events.append(event)
        if event["event"] == "voice_segment":
            delivered.set()
    assert next(index for index, event in enumerate(events) if event["event"] == "voice_segment") < next(
        index for index, event in enumerate(events) if event.get("text") == "还没有结束的下一句。"
    )


async def test_failed_or_timed_out_segment_does_not_fail_text_or_later_audio():
    async def synthesize(text, context):
        if text.startswith("第一"):
            raise RuntimeError("secret upstream response must not be exposed")
        return {"audio_url": "/ok.mp3", "duration_ms": 200}

    events = [event async for event in stream_voice_events(source_events(), synthesize, turn_id="t")]
    assert [event["event"] for event in events if event["event"].startswith("voice_segment")] == [
        "voice_segment_error",
        "voice_segment",
    ]
    assert "secret" not in str(events)
    assert events[-1]["_state"]["voice_error"] and len(events[-1]["_state"]["voice_segments"]) == 1


async def test_disconnect_closes_source_and_all_synthesis_workers():
    started, source_closed = asyncio.Event(), asyncio.Event()
    active = set()

    async def source():
        try:
            yield {"event": "meta"}
            for index in range(50):
                yield {"event": "token", "text": f"第{index}句这是一段足够长的话。"}
        finally:
            source_closed.set()

    async def synthesize(text, context):
        active.add(text)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active.remove(text)

    stream = stream_voice_events(source(), synthesize, turn_id="t")
    assert (await anext(stream))["event"] == "meta"
    await started.wait()
    await stream.aclose()
    assert source_closed.is_set() and not active


async def test_segment_timeouts_are_bounded_and_text_still_finishes():
    async def synthesize(*args):
        await asyncio.Event().wait()

    events = [
        event async for event in stream_voice_events(source_events(), synthesize, turn_id="t", timeout_seconds=0.02)
    ]
    assert len([event for event in events if event["event"] == "voice_segment_error"]) == 2
    assert events[-1]["event"] == "done" and events[-1]["_state"]["voice_error"]


@pytest.mark.parametrize("supports", [False, True])
async def test_host_negotiates_segmented_voice_and_skips_duplicate_full_synthesis(monkeypatch, supports):
    import core_orchestrator.state_machine as sm
    from shared_contracts.models import TurnContext, UserProfile
    from shared_runtime.config import get_settings

    async def passthrough(state):
        return state

    async def classify(state):
        state["intent"] = "chat"
        return state

    async def tokens(*args, **kwargs):
        yield "第一句话有八个字符。第二句话也有八个字符。"

    monkeypatch.setattr(sm, "get_settings", lambda: get_settings().model_copy(update={"enable_voice": True}))
    monkeypatch.setattr(sm, "_is_monolithic", lambda: True)
    monkeypatch.setattr(sm, "_stream_response_monolithic", tokens)
    monkeypatch.setattr(sm, "node_classify_intent", classify)
    for name in [
        "node_receive",
        "node_recall_memory",
        "prepare_reaction_state",
        "prepare_reply_decision",
        "node_generate_action",
        "node_send_response",
        "node_sync_memory",
    ]:
        monkeypatch.setattr(sm, name, passthrough)
    response = type("Response", (), {"json": lambda self: {"audio_url": "/voice/audio.mp3", "duration_ms": 100}})()
    post = AsyncMock(return_value=response)
    monkeypatch.setattr(sm.voice_client, "post", post)
    tc = TurnContext(
        turn_id="t",
        session_id="s",
        user=UserProfile(user_id="u"),
        platform="app",
        user_message="讲两句话",
        request_voice_reply=True,
        supports_segmented_voice=supports,
    )
    events = [event async for event in sm.stream_assistant_response(tc)]
    assert post.await_count == (2 if supports else 1)
    assert bool([event for event in events if event["event"] == "voice_segment"]) == supports
    state = events[-1]["_state"]
    assert state.get("voice_mode") == ("segmented" if supports else None)
    assert state.get("voice_url") == (None if supports else "/voice/audio.mp3")
