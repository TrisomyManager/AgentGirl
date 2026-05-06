"""Regression tests for OpenAI / Anthropic base URL normalization."""

from __future__ import annotations

from shared.llm_client import _normalize_anthropic_messages_base, _normalize_openai_chat_base


def test_normalize_openai_appends_v1_for_official_host() -> None:
    assert _normalize_openai_chat_base("https://api.openai.com") == "https://api.openai.com/v1"
    assert _normalize_openai_chat_base("https://api.openai.com/") == "https://api.openai.com/v1"
    assert _normalize_openai_chat_base("https://api.openai.com/v1") == "https://api.openai.com/v1"
    assert _normalize_openai_chat_base("https://api.openai.com/v1/") == "https://api.openai.com/v1"


def test_normalize_openai_leaves_custom_gateways() -> None:
    u = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert _normalize_openai_chat_base(u) == u.rstrip("/")


def test_normalize_anthropic_appends_v1() -> None:
    assert _normalize_anthropic_messages_base("https://api.anthropic.com") == "https://api.anthropic.com/v1"
    assert _normalize_anthropic_messages_base("https://api.anthropic.com/v1") == "https://api.anthropic.com/v1"
