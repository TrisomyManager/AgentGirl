"""Unified async LLM client for all companion-ai modules."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional
from urllib.parse import urlparse

import httpx
import structlog

from shared.config import get_settings

logger = structlog.get_logger("shared.llm_client")

# Persist next to companion-ai/.env so cwd does not change where config is read/written.
_COMPANION_ROOT = Path(__file__).resolve().parent.parent

_OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
_ANTHROPIC_DEFAULT_BASE = "https://api.anthropic.com/v1"
_DEFAULT_TIMEOUT = 60.0
_POSITIVE_HINTS = (
    "开心",
    "高兴",
    "喜欢",
    "爱",
    "谢谢",
    "太好了",
    "不错",
    "棒",
    "期待",
    "哈哈",
    "幸福",
)
_NEGATIVE_HINTS = (
    "难过",
    "伤心",
    "烦",
    "累",
    "生气",
    "焦虑",
    "害怕",
    "崩溃",
    "讨厌",
    "失眠",
    "孤独",
    "压力",
)


# ---------------------------------------------------------------------------
# Runtime config — updated via POST /settings/llm without restart
# ---------------------------------------------------------------------------

_runtime_llm_config: Dict[str, Any] = {}
_CONFIG_FILE = Path(
    os.getenv("COMPANION_LLM_CONFIG_PATH", str(_COMPANION_ROOT / "companion_llm_config.json"))
)


def _normalize_openai_chat_base(url: str) -> str:
    """OpenAI chat completions live under ``.../v1``; bare ``https://api.openai.com`` breaks."""
    b = (url or "").strip().rstrip("/")
    if not b or b.lower().endswith("/v1"):
        return b
    try:
        host = (urlparse(b).hostname or "").lower()
    except Exception:
        return b
    if host == "api.openai.com":
        return f"{b}/v1"
    return b


def _normalize_anthropic_messages_base(url: str) -> str:
    """Anthropic Messages API is ``.../v1/messages``."""
    b = (url or "").strip().rstrip("/")
    if not b or b.lower().endswith("/v1"):
        return b
    try:
        host = (urlparse(b).hostname or "").lower()
    except Exception:
        return b
    if host == "api.anthropic.com":
        return f"{b}/v1"
    return b


def update_runtime_llm_config(**kwargs: Any) -> None:
    """Merge kwargs into the runtime LLM config (empty string clears a key)."""
    for k, v in kwargs.items():
        if v == "":
            _runtime_llm_config.pop(k, None)
        else:
            _runtime_llm_config[k] = v


def get_runtime_llm_config() -> Dict[str, Any]:
    return dict(_runtime_llm_config)


def save_llm_config_to_disk() -> None:
    """Persist runtime LLM config to disk so it survives restarts."""
    try:
        _CONFIG_FILE.write_text(json.dumps(_runtime_llm_config, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("llm_config.save_failed", path=str(_CONFIG_FILE), error=str(exc))


def load_llm_config_from_disk() -> None:
    """Load persisted LLM config from disk into runtime config on startup."""
    if not _CONFIG_FILE.exists():
        return
    try:
        data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _runtime_llm_config.update(data)
            logger.info("llm_config.loaded_from_disk", path=str(_CONFIG_FILE), keys=list(data.keys()))
    except Exception as exc:
        logger.warning("llm_config.load_failed", path=str(_CONFIG_FILE), error=str(exc))


async def chunk_text_stream(
    text: str,
    chunk_size: int = 3,
    delay_seconds: float = 0.04,
) -> AsyncIterator[str]:
    """Emit ``text`` as small async chunks.

    Used when the active provider does not stream (e.g. rule-based fallback)
    so that the public ``/orchestrator/turn/stream`` SSE contract still gives
    callers an incremental experience.
    """
    if not text:
        return
    for start in range(0, len(text), chunk_size):
        yield text[start:start + chunk_size]
        if delay_seconds:
            await asyncio.sleep(delay_seconds)


class LLMClient:
    """Async LLM client with multi-provider support and local fallbacks."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        openai_base_url: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        anthropic_base_url: Optional[str] = None,
        default_model: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        rt = _runtime_llm_config  # runtime overrides win over env/settings

        self.openai_api_key = openai_api_key or rt.get("openai_api_key") or settings.openai_api_key
        self.openai_base_url = _normalize_openai_chat_base(
            (openai_base_url or rt.get("openai_base_url") or settings.openai_base_url or _OPENAI_DEFAULT_BASE).rstrip(
                "/"
            )
        )
        self.anthropic_api_key = anthropic_api_key or rt.get("anthropic_api_key") or settings.anthropic_api_key
        self.anthropic_base_url = _normalize_anthropic_messages_base(
            (
                anthropic_base_url
                or rt.get("anthropic_base_url")
                or settings.anthropic_base_url
                or _ANTHROPIC_DEFAULT_BASE
            ).rstrip("/")
        )
        self.default_model = default_model or rt.get("default_model") or settings.default_llm_model
        self._http: Optional[httpx.AsyncClient] = None

    def has_configured_provider(self) -> bool:
        return bool(self.openai_api_key or self.anthropic_api_key)

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _detect_provider(self) -> str:
        if self.openai_api_key:
            return "openai"
        if self.anthropic_api_key:
            return "anthropic"
        raise RuntimeError(
            "No LLM API key configured. Set COMPANION_OPENAI_API_KEY or COMPANION_ANTHROPIC_API_KEY."
        )

    def _rule_based_sentiment(self, user_message: str) -> str:
        text = user_message.lower()
        if any(token in text for token in _NEGATIVE_HINTS):
            return "negative"
        if any(token in text for token in _POSITIVE_HINTS):
            return "positive"
        return "neutral"

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = 1024,
    ) -> Dict[str, Any]:
        """Generate a chat completion. Returns assistant_message, tokens_used, model."""
        provider = self._detect_provider()
        chosen_model = model or self.default_model

        if provider == "openai":
            return await self._generate_openai(
                system_prompt=system_prompt,
                user_message=user_message,
                model=chosen_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        return await self._generate_anthropic(
            system_prompt=system_prompt,
            user_message=user_message,
            model=chosen_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def generate_stream(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = 1024,
    ) -> AsyncIterator[str]:
        """Stream a chat completion as incremental text chunks.

        Yields the same per-token deltas the upstream API emits. Callers can
        concatenate the chunks to reconstruct the full assistant_message.
        Falls back to chunk-by-chunk emission of the non-streaming response
        when the provider does not support SSE.
        """
        provider = self._detect_provider()
        chosen_model = model or self.default_model

        if provider == "openai":
            iterator = self._generate_openai_stream(
                system_prompt=system_prompt,
                user_message=user_message,
                model=chosen_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            iterator = self._generate_anthropic_stream(
                system_prompt=system_prompt,
                user_message=user_message,
                model=chosen_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        async for token in iterator:
            if token:
                yield token

    async def _generate_openai(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> Dict[str, Any]:
        url = f"{self.openai_base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        logger.debug("llm.openai_request", model=model, url=url)
        resp = await self.http.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        return {
            "assistant_message": choice["message"]["content"],
            "tokens_used": data.get("usage", {}).get("total_tokens", 0),
            "model": data.get("model", model),
        }

    async def _generate_anthropic(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> Dict[str, Any]:
        url = f"{self.anthropic_base_url}/messages"
        payload: Dict[str, Any] = {
            "model": model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
            "max_tokens": max_tokens or 1024,
        }
        if temperature is not None:
            payload["temperature"] = temperature

        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        logger.debug("llm.anthropic_request", model=model, url=url)
        resp = await self.http.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        assistant_message = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        tokens_used = data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)

        return {
            "assistant_message": assistant_message,
            "tokens_used": tokens_used,
            "model": data.get("model", model),
        }

    async def _generate_openai_stream(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> AsyncIterator[str]:
        url = f"{self.openai_base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        logger.debug("llm.openai_stream_request", model=model, url=url)
        async with self.http.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                err_body = await resp.aread()
                raise RuntimeError(
                    f"LLM HTTP {resp.status_code}: {err_body.decode('utf-8', errors='ignore')}"
                )
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except Exception:
                    continue
                delta = obj.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content")
                if token:
                    yield token

    async def _generate_anthropic_stream(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> AsyncIterator[str]:
        url = f"{self.anthropic_base_url}/messages"
        payload: Dict[str, Any] = {
            "model": model,
            "stream": True,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
            "max_tokens": max_tokens or 1024,
        }
        if temperature is not None:
            payload["temperature"] = temperature

        headers = {
            "x-api-key": self.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        logger.debug("llm.anthropic_stream_request", model=model, url=url)
        async with self.http.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                err_body = await resp.aread()
                raise RuntimeError(
                    f"LLM HTTP {resp.status_code}: {err_body.decode('utf-8', errors='ignore')}"
                )
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    obj = json.loads(data)
                except Exception:
                    continue
                event_type = obj.get("type")
                if event_type == "content_block_delta":
                    delta = obj.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        token = delta.get("text")
                        if token:
                            yield token
                elif event_type == "message_stop":
                    break

    async def analyze_sentiment(self, user_message: str) -> str:
        """Analyze sentiment. Returns 'positive', 'negative', or 'neutral'."""
        if not self.has_configured_provider():
            return self._rule_based_sentiment(user_message)

        prompt = (
            "Analyze the sentiment of the following message and answer with exactly one word: "
            "positive, negative, or neutral.\n"
            f"Message: {user_message}"
        )
        try:
            result = await self.generate(
                system_prompt="You are a sentiment classifier. Answer with one word only.",
                user_message=prompt,
                temperature=0.0,
                max_tokens=10,
            )
            raw = result["assistant_message"].strip().lower()
            if "positive" in raw:
                return "positive"
            if "negative" in raw:
                return "negative"
            return "neutral"
        except Exception as exc:
            logger.warning("sentiment_analysis_failed", error=str(exc))
            return self._rule_based_sentiment(user_message)

    async def generate_with_emotion(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = 1024,
    ) -> Dict[str, Any]:
        """Generate response and analyze sentiment."""
        sentiment = await self.analyze_sentiment(user_message)
        result = await self.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        result["sentiment"] = sentiment
        return result
