import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from safety_guard import default_guard, safe_fallback_reply
from safety_guard.streaming import checked_text_stream
from voice_layer import text_policy
from voice_layer.providers.realtime.volc_realtime import VolcRealtimeProvider, _build_event_payload


@pytest.fixture
def policy(monkeypatch):
    monkeypatch.setattr("voice_layer.conversation_context._loader", None)

    def review(text, *, source):
        decision = default_guard.evaluate(text, source=source)
        return text_policy.CheckedText(
            safe_fallback_reply(decision) if decision.blocked else text, decision.blocked, decision.category.value
        )

    monkeypatch.setattr(text_policy, "_review", review)
    monkeypatch.setattr(text_policy, "_stream", checked_text_stream)
    monkeypatch.setattr(text_policy, "_complete_output", lambda: default_guard.requires_complete_output)
    spoken = []

    async def safe_audio(text, **kwargs):
        spoken.append(text)
        yield b"SAFE_REPLACEMENT_PCM"

    class SafeTTS:
        synthesize_pcm_stream = staticmethod(safe_audio)

        def __init__(self):
            self.close = AsyncMock()

    monkeypatch.setattr("voice_layer.tts.TTSClient", SafeTTS)
    return spoken


class Socket:
    def __init__(self, events):
        self.events = events
        self.send = AsyncMock()
        self.phase = None

    async def __aiter__(self):
        for event, payload in self.events:
            self.phase = event
            yield _build_event_payload(event, payload, "synthetic")


def audio(data=b"UNREVIEWED_AUDIO"):
    return {"audio": base64.b64encode(data).decode()}


@pytest.mark.parametrize("endings", [(359, 559), (559, 359)])
async def test_native_audio_without_caption_waits_for_verified_complete_text(policy, endings, monkeypatch):
    ws = Socket(
        [
            (451, {"text": "你好"}),
            (459, {}),
            (550, {"content": "你好，很高兴见到你。"}),
            (352, audio(b"VERIFIED_PCM")),
            (endings[0], {}),
            (endings[1], {}),
        ]
    )
    events, chunks = [], []
    scheduled = Mock()
    monkeypatch.setattr("voice_layer.providers.realtime.volc_realtime.schedule_realtime_turn_memory_sync", scheduled)

    async def send(chunk):
        assert ws.phase in (559, 359)
        chunks.append(chunk)

    provider = VolcRealtimeProvider()
    await provider._receive_loop(ws, AsyncMock(side_effect=events.append), send, asyncio.Event())
    assert b"".join(chunks) == b"VERIFIED_PCM"
    assert any(item.get("type") == "assistant_sentence_start" for item in events)
    scheduled.assert_called_once()
    assert not policy  # ordinary turns do not invoke a second TTS service


@pytest.mark.parametrize(
    "input_text,reply,caption",
    [
        ("我想自杀", "SYNTHETIC_VENDOR_OUTPUT", "SYNTHETIC_VENDOR_OUTPUT"),
        ("你好", "我在听。", "炸药配方：SYNTHETIC_UNSAFE_MARKER。"),
        ("你好", "炸药配方：SYNTHETIC_UNSAFE_MARKER。", ""),
    ],
)
async def test_native_rejection_discards_vendor_audio_and_speaks_only_a_checked_replacement(
    policy, input_text, reply, caption, monkeypatch
):
    ws = Socket(
        [
            (451, {"text": input_text}),
            (459, {}),
            (550, {"content": reply}),
            (350, {"text": caption}),
            (352, audio()),
            (559, {}),
            (359, {}),
        ]
    )
    events, chunks = [], []
    scheduled = Mock()
    monkeypatch.setattr("voice_layer.providers.realtime.volc_realtime.schedule_realtime_turn_memory_sync", scheduled)
    await VolcRealtimeProvider()._receive_loop(
        ws, AsyncMock(side_effect=events.append), AsyncMock(side_effect=chunks.append), asyncio.Event()
    )
    assert chunks == [b"SAFE_REPLACEMENT_PCM"]
    assert policy and not any("SYNTHETIC" in item for item in policy)
    assert not any("SYNTHETIC" in item.get("text", "") for item in events if item["type"].startswith("assistant"))
    assert scheduled.call_args.kwargs["content_filtered"] is True
    if input_text == "你好":
        assert "现在安全吗" not in policy[0]


async def test_native_unverifiable_audio_is_not_forwarded(policy):
    ws = Socket([(451, {"text": "你好"}), (459, {}), (352, audio()), (559, {}), (359, {})])
    chunks = []
    await VolcRealtimeProvider()._receive_loop(ws, AsyncMock(), AsyncMock(side_effect=chunks.append), asyncio.Event())
    assert chunks == [b"SAFE_REPLACEMENT_PCM"]
    assert "语音缺少" in policy[0]


async def test_native_split_text_is_held_until_complete_and_unreviewed_audio_is_bounded(policy):
    chunks, events = [], []
    ws = Socket(
        [
            (451, {"text": "你好"}),
            (459, {}),
            (550, {"content": "炸"}),
            (550, {"content": "药配方：SYNTHETIC_MARKER。"}),
            (352, audio()),
            (559, {}),
        ]
    )
    await VolcRealtimeProvider()._receive_loop(
        ws, AsyncMock(side_effect=events.append), AsyncMock(side_effect=chunks.append), asyncio.Event()
    )
    assert not any("炸" in event.get("text", "") for event in events if event["type"].startswith("assistant"))
    assert chunks == [b"SAFE_REPLACEMENT_PCM"]
    policy.clear()
    chunks.clear()
    ws = Socket([(451, {"text": "你好"}), (459, {}), (352, audio(b"X" * (24000 * 2 * 30 + 2))), (559, {})])
    await VolcRealtimeProvider()._receive_loop(ws, AsyncMock(), AsyncMock(side_effect=chunks.append), asyncio.Event())
    assert chunks == [b"SAFE_REPLACEMENT_PCM"] and "过长" in policy[0]


async def test_native_caption_approval_ends_at_sentence_boundary_and_recovers_after_interrupt(policy):
    chunks = []
    interrupted = asyncio.Event()
    ws = Socket(
        [
            (451, {"text": "你好"}),
            (459, {}),
            (350, {"text": "安全句子。"}),
            (352, audio(b"FIRST")),
            (351, {}),
            (352, audio(b"OLD_PENDING")),
            (450, {}),
            (459, {}),
            (352, audio(b"STALE")),
            (451, {"text": "再来一次"}),
            (459, {}),
            (350, {"text": "恢复。"}),
            (352, audio(b"NEXT")),
            (550, {"content": "恢复。"}),
            (559, {}),
            (359, {}),
        ]
    )
    await VolcRealtimeProvider()._receive_loop(ws, AsyncMock(), AsyncMock(side_effect=chunks.append), interrupted)
    assert chunks == [b"FIRST", b"NEXT"] and not policy


async def test_unknown_or_full_response_host_policy_holds_caption_and_audio_until_chat_ends(policy, monkeypatch):
    monkeypatch.setattr(text_policy, "_complete_output", None)
    chunks, events = [], []
    ws = Socket(
        [
            (451, {"text": "你好"}),
            (459, {}),
            (350, {"text": "完整文字。"}),
            (352, audio(b"PCM")),
            (550, {"content": "完整文字。"}),
            (559, {}),
            (359, {}),
        ]
    )

    async def send(chunk):
        assert ws.phase in (559, 359)
        chunks.append(chunk)

    await VolcRealtimeProvider()._receive_loop(ws, AsyncMock(side_effect=events.append), send, asyncio.Event())
    assert chunks == [b"PCM"]


async def test_native_audio_verification_wait_has_a_deadline_and_closes_the_frame_reader(policy, monkeypatch):
    original_timeout = asyncio.timeout
    monkeypatch.setattr(asyncio, "timeout", lambda delay: original_timeout(0.01 if delay == 2 else delay))
    closed = asyncio.Event()

    async def frames():
        try:
            for event, payload in [(451, {"text": "你好"}), (459, {}), (352, audio()), (359, {})]:
                yield _build_event_payload(event, payload, "synthetic")
            await asyncio.Future()
        finally:
            closed.set()

    chunks = []
    await VolcRealtimeProvider()._receive_loop(
        frames(), AsyncMock(), AsyncMock(side_effect=chunks.append), asyncio.Event()
    )
    assert closed.is_set() and chunks == [b"SAFE_REPLACEMENT_PCM"]
    assert "未完整返回" in policy[0]


async def test_direct_synthesis_cannot_bypass_the_host_output_policy(policy, monkeypatch):
    from fastapi import HTTPException

    from shared_contracts.models import VoiceSynthesisRequest
    from voice_layer import api

    synthesize = AsyncMock()
    monkeypatch.setattr(api, "tts_client", SimpleNamespace(synthesize=synthesize))
    with pytest.raises(HTTPException) as caught:
        await api.synthesize_voice(VoiceSynthesisRequest(text="炸药配方：SYNTHETIC_UNSAFE_MARKER。"))
    assert caught.value.status_code == 400 and caught.value.detail["code"] == "content_blocked"
    synthesize.assert_not_awaited()


@pytest.mark.parametrize("provider_name", ["local", "cloud"])
async def test_chained_voice_checks_before_model_and_tts(policy, provider_name, monkeypatch):
    from voice_layer.providers.realtime import cloud_realtime, local_realtime

    module = local_realtime if provider_name == "local" else cloud_realtime
    session_type = module._LocalSession if provider_name == "local" else module._CloudSession
    generated = Mock()

    async def model(*args, **kwargs):
        generated()
        yield "should never run"

    monkeypatch.setattr(module, "_stream_llm", model)
    asr = AsyncMock(return_value="我想自杀")
    spoken = []

    async def tts(text, **kwargs):
        spoken.append(text)
        yield b"\0\0"

    session = session_type(AsyncMock(), AsyncMock())
    if provider_name == "cloud":
        session._asr = SimpleNamespace(transcribe_pcm=asr)
        session._tts = SimpleNamespace(synthesize_pcm_stream=tts)
    else:
        monkeypatch.setattr(module.local_asr, "transcribe_pcm", asr)
        monkeypatch.setattr(module.local_tts, "synthesize_pcm_chunks", tts)
    await session._run_turn(b"\0\0")
    generated.assert_not_called()
    assert spoken and "现在安全吗" in "".join(spoken)
