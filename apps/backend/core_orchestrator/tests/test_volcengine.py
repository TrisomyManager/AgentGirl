"""Contract tests for Ark/Speech requests; no credentials or live API calls."""

import base64
import json
import struct
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from shared_runtime import llm_client, voice_runtime_config
from shared_runtime.config import Settings
from shared_runtime.model_presets import ARK_BASE_URL, CHAT_MODEL
from voice_layer.providers import volcengine
from voice_layer.providers.realtime.volc_realtime import (
    VolcRealtimeProvider,
    _build_event_payload,
    _parse_response,
    _redact_headers,
)


@pytest.fixture
def isolated(monkeypatch):
    monkeypatch.setattr("voice_layer.text_policy._review", None)
    monkeypatch.setattr("voice_layer.text_policy._stream", None)
    settings = Settings(_env_file=None, lite_mode=True, ark_api_key="ark-test", volc_api_key="speech-test")
    monkeypatch.setattr(llm_client, "_runtime_llm_config", {})
    monkeypatch.setattr(voice_runtime_config, "_runtime_voice_config", {})
    monkeypatch.setattr("shared_runtime.config.get_settings", lambda: settings)
    monkeypatch.setattr(llm_client, "get_settings", lambda: settings)
    monkeypatch.setattr("voice_layer.providers.realtime.volc_realtime.get_settings", lambda: settings)
    return settings


async def test_ark_chat_disables_thinking_for_fast_replies(isolated):
    def handle(req):
        assert str(req.url) == ARK_BASE_URL + "/chat/completions"
        assert req.headers["Authorization"] == "Bearer ark-test"
        payload = json.loads(req.content)
        assert payload["model"] == CHAT_MODEL
        assert payload["thinking"] == {"type": "disabled"}
        return httpx.Response(200, json={"choices": [{"message": {"content": "你好"}}]})

    client = llm_client.LLMClient()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        assert (await client.generate("你是测试助手", "你好"))["assistant_message"] == "你好"
    finally:
        await client.close()


async def test_memory_extraction_uses_ark_environment_key(isolated, monkeypatch):
    from memory_system import pipeline

    isolated.openai_base_url = "https://obsolete.test/v1"
    isolated.openai_api_key = "obsolete-key"

    def handle(req):
        assert str(req.url) == ARK_BASE_URL + "/chat/completions"
        assert req.headers["Authorization"] == "Bearer ark-test"
        payload = json.loads(req.content)
        assert payload["model"] == CHAT_MODEL
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"entities":[]}'}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(pipeline.httpx, "AsyncClient", lambda **_: client)
    result = await pipeline._llm_chat([{"role": "user", "content": "Extract JSON entities"}], json_mode=True)
    assert json.loads(result) == {"entities": []}


def test_memory_embedding_does_not_inherit_old_chat_provider(isolated, monkeypatch):
    from memory_system import vector_store

    monkeypatch.setattr(vector_store, "settings", isolated)
    llm_client.update_runtime_llm_config(
        provider="openai_compatible", openai_api_key="other-vendor-key", openai_base_url="https://obsolete.test/v1",
    )
    key, base_url, model, dim = vector_store._resolve_embedding_config()
    assert key == "ark-test" and base_url == ARK_BASE_URL
    assert model == "doubao-embedding-vision-251215" and dim == 1024


def test_intent_router_uses_ark_and_reloads_saved_chat_configuration(isolated, monkeypatch):
    from core_orchestrator.intent_router import IntentRouter

    isolated.intent_router_use_llm = True
    monkeypatch.setattr("core_orchestrator.intent_router.get_settings", lambda: isolated)
    router = IntentRouter()
    assert router._can_use_llm()
    first = router._get_llm()
    assert first.openai_api_key.get_secret_value() == "ark-test"
    assert first.openai_api_base == ARK_BASE_URL
    llm_client.update_runtime_llm_config(
        provider="volcengine", openai_api_key="runtime-ark", openai_base_url=ARK_BASE_URL,
        default_model="ep-chat-custom",
    )
    second = router._get_llm()
    assert second is not first
    assert second.openai_api_key.get_secret_value() == "runtime-ark"
    assert second.model_name == "ep-chat-custom"


async def test_speech_asr_uses_native_api_and_base64():
    def handle(req):
        assert req.url.path == "/api/v3/auc/bigmodel/recognize/flash"
        assert req.headers["X-Api-Key"] == "speech-test"
        assert "Authorization" not in req.headers
        assert req.headers["X-Api-Resource-Id"] == "volc.bigasr.auc_turbo"
        assert req.headers["X-Api-Sequence"] == "-1"
        assert base64.b64decode(json.loads(req.content)["audio"]["data"]) == b"RIFF-audio"
        return httpx.Response(200, headers={"X-Api-Status-Code": "20000000"}, json={"result": {"text": "你好朋友"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await volcengine.transcribe(
            client, b"RIFF-audio", api_key="speech-test", base_url="https://openspeech.bytedance.com",
            resource_id="volc.bigasr.auc_turbo",
        )
    assert result[0] == "你好朋友"


@pytest.mark.parametrize("status_code", ["45000001", "55000031"])
async def test_asr_http_200_can_still_be_vendor_failure(status_code):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
        200, headers={"X-Api-Status-Code": status_code, "X-Api-Message": "failed"}, json={},
    ))) as client:
        with pytest.raises(RuntimeError, match=status_code):
            await volcengine.transcribe(client, b"audio", api_key="test", base_url="https://test", resource_id="asr")


async def test_tts_stream_decodes_chunks_and_native_sample_rate():
    def handle(req):
        payload = json.loads(req.content)
        assert req.url.path == "/api/v3/tts/unidirectional"
        assert req.headers["X-Api-Key"] == "speech-test"
        assert req.headers["X-Api-Resource-Id"] == "seed-tts-2.0"
        assert payload["req_params"]["speaker"] == "zh_female_xiaohe_uranus_bigtts"
        assert payload["req_params"]["audio_params"]["format"] == "pcm"
        assert payload["req_params"]["audio_params"]["sample_rate"] == 16000
        return httpx.Response(200, text='{"code":0,"data":"AAE="}\n{"code":20000000}\n')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        chunks = [chunk async for chunk in volcengine.synthesize_stream(
            client, "你好", api_key="speech-test", base_url="https://test", resource_id="seed-tts-2.0",
            speaker="zh_female_xiaohe_uranus_bigtts", fmt="pcm", sample_rate=16000,
        )]
    assert b"".join(chunks) == b"\x00\x01"


@pytest.mark.parametrize("body", ['{"code":45000001,"message":"bad speaker"}\n', '{"code":0,"data":"AAE="}\n'])
async def test_tts_rejects_error_or_truncated_stream(body):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))) as client:
        with pytest.raises(RuntimeError):
            _ = [chunk async for chunk in volcengine.synthesize_stream(
                client, "你好", api_key="test", base_url="https://test", resource_id="tts", speaker="voice",
            )]


def test_realtime_request_has_event_and_session_before_payload():
    # Field positions follow the official StartSession example, independently of the decoder.
    frame = _build_event_payload(100, {"dialog": {}}, "session-1")
    assert frame[:4] == bytes([0x11, 0x14, 0x11, 0])
    assert frame[4:8] == struct.pack(">I", 100)
    assert frame[8:12] == struct.pack(">I", 9)
    assert frame[12:21] == b"session-1"
    assert struct.unpack(">I", frame[21:25])[0] == len(frame[25:])


def test_realtime_server_audio_keeps_every_pcm_byte():
    # Official TTSResponse layout: header, event=352, session length/id, payload length/audio.
    audio = b"\0\0\0\x01\xff\x7f"
    frame = bytes([0x11, 0xB4, 0, 0]) + struct.pack(">II", 352, 3) + b"sid"
    frame += struct.pack(">I", len(audio)) + audio
    parsed = _parse_response(frame)
    assert parsed["_session_id"] == "sid"
    assert parsed["_raw_payload"] == audio


async def test_realtime_new_key_auth_and_no_local_fallback(isolated, monkeypatch):
    # connect is a context-manager factory, rather than an awaited coroutine.
    from unittest.mock import Mock

    connect = Mock(side_effect=RuntimeError("stop before network"))
    monkeypatch.setattr("voice_layer.providers.realtime.volc_realtime.websockets.connect", connect)
    provider = VolcRealtimeProvider()
    await provider.run(AsyncMock(), AsyncMock(), AsyncMock())
    headers = connect.call_args.kwargs["additional_headers"]
    assert headers["X-Api-Key"] == "speech-test"
    assert "X-Api-Access-Key" not in headers
    assert "speech-test" not in json.dumps(_redact_headers(headers))


async def test_native_asr_and_chat_events_normalize_without_repeated_words(isolated):
    def frame(event, data):
        body = json.dumps(data).encode()
        return (bytes([0x11, 0x94, 0x10, 0]) + struct.pack(">II", event, 3) + b"sid"
                + struct.pack(">I", len(body)) + body)

    class Socket:
        def __aiter__(self):
            return self.events()

        async def events(self):
            for event in [frame(451, {"results": [{"text": "你好", "is_interim": True}]}),
                          frame(451, {"results": [{"text": "你好朋友", "is_interim": False}]}),
                          frame(459, {}), frame(550, {"content": "我在"})]:
                yield event

    send = AsyncMock()
    import asyncio

    await VolcRealtimeProvider()._receive_loop(Socket(), send, AsyncMock(), asyncio.Event())
    events = [call.args[0] for call in send.call_args_list]
    assert events == [{"type": "user_transcript_delta", "text": "你好"},
                      {"type": "user_transcript_delta", "text": "朋友"},
                      {"type": "user_transcript_final", "text": "你好朋友"},
                      {"type": "assistant_text_delta", "text": "我在"}]


async def test_ark_embedding_uses_multimodal_endpoint_for_endpoint_id(isolated, monkeypatch):
    from memory_system import vector_store

    isolated.embedding_model = "ep-test-embedding"
    isolated.embedding_dim = 4
    monkeypatch.setattr(vector_store, "settings", isolated)

    def handle(req):
        assert req.url.path == "/api/v3/embeddings/multimodal"
        payload = json.loads(req.content)
        assert payload["model"] == "ep-test-embedding"
        assert payload["input"] == [{"type": "text", "text": "喜欢猫"}]
        return httpx.Response(200, json={"data": {"embedding": [0.1, 0.2, 0.3, 0.4]}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(vector_store.httpx, "AsyncClient", lambda **_: client)
    assert await vector_store._get_embedding("喜欢猫") == [0.1, 0.2, 0.3, 0.4]


async def test_settings_preserve_key_and_invalid_update_is_atomic(isolated, monkeypatch):
    from core_orchestrator import api

    monkeypatch.setattr(api, "get_settings", lambda: isolated)
    monkeypatch.setattr(api, "save_llm_config_to_disk", lambda: None)
    response = await api.save_llm_settings(api.LlmConfigRequest(provider="volcengine", api_key="saved-test"))
    assert response.base_url == ARK_BASE_URL and response.model == CHAT_MODEL
    assert response.api_key_set and "saved-test" not in response.model_dump_json()
    await api.save_llm_settings(api.LlmConfigRequest(provider="volcengine", model="ep-custom-chat"))
    assert llm_client.get_runtime_llm_config()["openai_api_key"] == "saved-test"
    before = llm_client.get_runtime_llm_config()
    with pytest.raises(HTTPException):
        await api.save_llm_settings(api.LlmConfigRequest(provider="unsupported"))
    assert llm_client.get_runtime_llm_config() == before


async def test_voice_settings_env_matches_clients_and_keeps_keys(isolated, monkeypatch):
    from core_orchestrator import api
    from voice_layer.asr import ASRClient
    from voice_layer.tts import TTSClient

    monkeypatch.setattr(api, "get_settings", lambda: isolated)
    monkeypatch.setattr(api, "save_voice_config_to_disk", lambda: None)
    monkeypatch.setattr(api, "_reload_voice_clients", lambda: None)
    response = await api.get_voice_settings()
    assert response.asr_api_key_set and response.tts_api_key_set and response.volc_api_key_set
    assert ASRClient().provider == "volcengine" and TTSClient().provider == "volcengine"
    assert "speech-test" not in response.model_dump_json()
    await api.save_voice_settings(api.VoiceConfigRequest(
        asr_base_url=response.asr_base_url, asr_model=response.asr_model,
        tts_provider=response.tts_provider, tts_base_url=response.tts_base_url,
        tts_model=response.tts_model, tts_voice_id=response.tts_voice_id,
    ))
    assert voice_runtime_config.get_runtime_voice_config()["volc_api_key"] == "speech-test"
    await api.save_voice_settings(api.VoiceConfigRequest(reset=True))
    assert voice_runtime_config.get_runtime_voice_config() == {}
    # Explicit environment credentials remain visible after resetting runtime overrides.
    assert (await api.get_voice_settings()).volc_api_key_set


def test_switching_vendor_does_not_reuse_speech_environment_key(isolated):
    voice_runtime_config.update_runtime_voice_config(
        asr_base_url="https://other.test", tts_provider="openai", tts_base_url="https://other.test",
    )
    config = voice_runtime_config.get_effective_voice_config()
    assert not config["asr_api_key"] and not config["tts_api_key"]


def test_switching_vendor_does_not_reuse_ark_environment_key(isolated):
    llm_client.update_runtime_llm_config(provider="openai", openai_base_url="https://other.test")
    assert not llm_client.LLMClient().has_configured_provider()


async def test_realtime_round_trip_over_local_websocket(isolated):
    """Use the real websocket library against a local fake vendor, without network services."""
    import asyncio

    from websockets.asyncio.server import serve

    def server_frame(event, body, *, audio=False):
        data = body if audio else json.dumps(body).encode()
        identifier = b"connect" if event < 100 else b"session"
        header = bytes([0x11, 0xB4 if audio else 0x94, 0 if audio else 0x10, 0])
        return (header + struct.pack(">II", event, len(identifier)) + identifier
                + struct.pack(">I", len(data)) + data)

    async def vendor(ws):
        assert ws.request.headers["X-Api-Key"] == "speech-test"
        assert _parse_response(await ws.recv())["_event_id"] == 1
        await ws.send(server_frame(50, {}))
        session = _parse_response(await ws.recv())
        assert session["_event_id"] == 100
        assert session["dialog"]["extra"]["model"] == "1.2.1.1"
        assert session["tts"]["audio_config"]["format"] == "pcm_s16le"
        await ws.send(server_frame(150, {}))
        audio = _parse_response(await ws.recv())
        assert audio["_event_id"] == 200 and audio["_raw_payload"] == b"\x00\x01" * 160
        assert _parse_response(await ws.recv())["_event_id"] == 400
        for event, data in [(451, {"results": [{"text": "你好", "is_interim": False}]}),
                            (459, {}), (550, {"content": "我在"}), (350, {"text": "我在"})]:
            await ws.send(server_frame(event, data))
        await ws.send(server_frame(352, b"\x00\x01", audio=True))
        await ws.send(server_frame(359, {}))
        assert _parse_response(await ws.recv())["_event_id"] == 102

    queue = asyncio.Queue()
    queue.put_nowait({"type": "binary", "data": b"\x00\x01" * 160})
    queue.put_nowait({"type": "text", "data": '{"type":"speech_end"}'})
    events, audio_chunks = [], []

    async def send_json(event):
        events.append(event)
        if event["type"] == "assistant_audio_done":
            queue.put_nowait({"type": "disconnect"})

    async def send_bytes(data):
        audio_chunks.append(data)

    async with serve(vendor, "127.0.0.1", 0) as server:
        isolated.volc_endpoint = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        await asyncio.wait_for(VolcRealtimeProvider().run(send_json, send_bytes, queue.get), timeout=5)
    assert events[0]["type"] == "ready"
    assert not any(event["type"] == "error" for event in events)
    assert {"type": "user_transcript_final", "text": "你好"} in events
    assert audio_chunks == [b"\x00\x01"]
