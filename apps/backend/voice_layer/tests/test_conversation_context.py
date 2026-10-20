import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from voice_layer.conversation_context import (
    VoiceConversationContext,
    load_conversation_context,
    set_conversation_context_loader,
)
from voice_layer.providers.realtime.volc_realtime import VolcRealtimeProvider, _build_event_payload, _parse_response


async def test_context_failure_does_not_silently_switch_to_another_personality():
    set_conversation_context_loader(AsyncMock(side_effect=ValueError("private content")))
    with pytest.raises(RuntimeError, match="人格与记忆") as error:
        await load_conversation_context(user_id="u", session_id="s", turn_id="t")
    assert "private content" not in str(error.value)


async def test_context_cancellation_propagates_and_cleans_up():
    entered, closed = asyncio.Event(), asyncio.Event()

    async def loader(**kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    set_conversation_context_loader(loader)
    task = asyncio.create_task(load_conversation_context(user_id="u", session_id="s", turn_id="t"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


async def test_native_connection_uses_host_personality_and_identity(monkeypatch):
    loader = AsyncMock(return_value=VoiceConversationContext("来自文字聊天的人格与记忆"))
    set_conversation_context_loader(loader)
    provider = VolcRealtimeProvider(app_id="test", access_token="test")
    provider._model = "2.0"
    ws = SimpleNamespace(send=AsyncMock())
    connection = Mock()
    connection.__aenter__ = AsyncMock(return_value=ws)
    connection.__aexit__ = AsyncMock()
    monkeypatch.setattr("voice_layer.providers.realtime.volc_realtime.websockets.connect", lambda *a, **k: connection)
    monkeypatch.setattr(provider, "_wait_connection_started", AsyncMock())
    monkeypatch.setattr(provider, "_wait_session_started", AsyncMock())
    monkeypatch.setattr(provider, "_run_session_loops", AsyncMock())
    await provider.run(AsyncMock(), AsyncMock(), AsyncMock(), memory_user_id="alice", memory_session_id="chat-1")
    assert loader.call_args.kwargs["user_id"] == "alice"
    assert loader.call_args.kwargs["session_id"] == "chat-1"
    config = _parse_response(ws.send.call_args_list[1].args[0])
    assert config["dialog"]["character_manifest"] == "来自文字聊天的人格与记忆"


@pytest.mark.parametrize("endings", [(559, 359), (359, 559)])
async def test_native_turn_persists_once_after_text_and_real_audio(endings, monkeypatch):
    provider = VolcRealtimeProvider()
    provider._memory_user_id, provider._memory_session_id = "alice", "chat-1"
    scheduled = Mock()
    monkeypatch.setattr("voice_layer.providers.realtime.volc_realtime.schedule_realtime_turn_memory_sync", scheduled)

    async def frames():
        for event, payload in [(451, {"text": "我喜欢喝茶"}), (459, {}),
                               (550, {"content": "记住了。"}), (352, {"audio": "AAAA"}),
                               (endings[0], {}), (endings[1], {}), (559, {}), (359, {})]:
            yield _build_event_payload(event, payload, "test")

    send_json = AsyncMock()
    await provider._receive_loop(frames(), send_json, AsyncMock(), asyncio.Event())
    scheduled.assert_called_once()
    data = scheduled.call_args.kwargs
    assert (data["user_id"], data["session_id"], data["user_message"], data["assistant_message"]) == (
        "alice", "chat-1", "我喜欢喝茶", "记住了。",
    )
    assert data["turn_id"]
    assert sum(call.args[0]["type"] == "turn_done" for call in send_json.call_args_list) == 1


@pytest.mark.parametrize("interrupted", [True, False])
async def test_native_partial_or_silent_turn_is_not_committed(interrupted, monkeypatch):
    provider = VolcRealtimeProvider()
    scheduled = Mock()
    monkeypatch.setattr("voice_layer.providers.realtime.volc_realtime.schedule_realtime_turn_memory_sync", scheduled)

    async def frames():
        events = [(451, {"text": "你好"}), (459, {}), (550, {"content": "没有听完的回答"})]
        if interrupted:
            events += [(450, {}), (352, {"audio": "AAAA"})]
        events += [(559, {}), (359, {})]
        for event, data in events:
            yield _build_event_payload(event, data, "test")

    await provider._receive_loop(frames(), AsyncMock(), AsyncMock(), asyncio.Event())
    scheduled.assert_not_called()


async def test_native_rejects_identity_change_without_reusing_vendor_history():
    provider = VolcRealtimeProvider()
    provider._memory_user_id, provider._memory_session_id = "alice", "s"
    send = AsyncMock()
    receive = AsyncMock(return_value={"type": "text", "data": json.dumps({"type": "start", "user_id": "bob"})})
    await provider._send_loop(SimpleNamespace(send=AsyncMock()), receive, asyncio.Event(), send)
    assert send.call_args.args[0]["type"] == "error"
    receive.assert_awaited_once()


@pytest.mark.parametrize("provider_name", ["local", "cloud"])
async def test_chained_providers_use_current_user_context_and_return_it_to_host(provider_name, monkeypatch):
    from voice_layer.providers.realtime import cloud_realtime, local_realtime

    context = VoiceConversationContext("用户 alice 喜欢茶", temperature=0.45, max_tokens=256)
    loader = AsyncMock(return_value=context)
    set_conversation_context_loader(loader)
    module = local_realtime if provider_name == "local" else cloud_realtime
    session_type = module._LocalSession if provider_name == "local" else module._CloudSession
    options = {}

    async def stream(history, **kwargs):
        options.update(kwargs)
        yield "我在听。"

    async def synthesize(*args, **kwargs):
        yield b"\0\0"

    monkeypatch.setattr(module, "_stream_llm", stream)
    session = session_type(AsyncMock(), AsyncMock(), memory_user_id="alice", memory_session_id="s")
    asr = AsyncMock(return_value="我失眠了")
    if provider_name == "cloud":
        session._asr = SimpleNamespace(transcribe_pcm=asr)
        session._tts = SimpleNamespace(synthesize_pcm_stream=synthesize)
    else:
        monkeypatch.setattr(local_realtime.local_asr, "transcribe_pcm", asr)
        monkeypatch.setattr(local_realtime.local_tts, "synthesize_pcm_chunks", synthesize)
    scheduled = Mock()
    monkeypatch.setattr("voice_layer.realtime_memory_sync.schedule_realtime_turn_memory_sync", scheduled)
    await session._run_turn(b"\0\0")
    assert options == {"system_prompt": context.system_prompt, "temperature": 0.45, "max_tokens": 256}
    assert loader.call_args.kwargs["user_message"] == "我失眠了"
    assert scheduled.call_args.kwargs["turn_id"] == loader.call_args.kwargs["turn_id"]
    assert scheduled.call_args.kwargs["conversation_context"] is context
