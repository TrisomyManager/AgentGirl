import pytest

from voice_layer.providers.realtime._llm_stream import _extract_openai_delta


def test_extract_openai_delta_skips_empty_choices_chunk():
    token = _extract_openai_delta('{"id":"chunk","choices":[]}', model="test-model")

    assert token is None


def test_extract_openai_delta_reads_content_token():
    token = _extract_openai_delta(
        '{"choices":[{"delta":{"content":"hello"}}]}',
        model="test-model",
    )

    assert token == "hello"


def test_extract_openai_delta_raises_clear_upstream_error():
    with pytest.raises(RuntimeError, match="bad model"):
        _extract_openai_delta(
            '{"error":{"message":"bad model"}}',
            model="test-model",
        )
