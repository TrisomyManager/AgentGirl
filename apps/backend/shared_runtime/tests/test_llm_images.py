import json

import httpx
import pytest

from shared_runtime.llm_client import LLMClient

IMAGE = "data:image/jpeg;base64,/9j/"


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_multimodal_wire_formats_for_both_generation_paths(provider, streaming):
    def handle(request):
        payload = json.loads(request.content)
        blocks = payload["messages"][-1]["content"]
        assert blocks[0] == {"type": "text", "text": "describe"}
        if provider == "anthropic":
            assert blocks[1] == {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": "/9j/"},
            }
            response = {"content": [{"type": "text", "text": "red"}]}
            events = [
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "red"}},
                {"type": "message_stop"},
            ]
        else:
            assert blocks[1] == {"type": "image_url", "image_url": {"url": IMAGE}}
            response = {"choices": [{"message": {"content": "red"}}]}
            events = [{"choices": [{"delta": {"content": "red"}}]}]
        if streaming:
            return httpx.Response(
                200, text="".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n"
            )
        return httpx.Response(200, json=response)

    client = LLMClient(openai_api_key="test-key")
    if provider == "anthropic":
        client.openai_api_key, client.anthropic_api_key = None, "test-key"
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    try:
        if streaming:
            assert (
                "".join([part async for part in client.generate_stream("system", "describe", image_urls=[IMAGE])])
                == "red"
            )
        else:
            assert (await client.generate("system", "describe", image_urls=[IMAGE]))["assistant_message"] == "red"
    finally:
        await client.close()


@pytest.mark.parametrize("streaming", [False, True])
async def test_upstream_errors_cannot_echo_private_images(streaming):
    client = LLMClient(openai_api_key="test-key")
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(400, text=IMAGE)))
    try:
        with pytest.raises(RuntimeError, match="图片识别失败") as error:
            if streaming:
                _ = [part async for part in client.generate_stream("s", "u", image_urls=[IMAGE])]
            else:
                await client.generate("s", "u", image_urls=[IMAGE])
        assert IMAGE not in str(error.value)
    finally:
        await client.close()
