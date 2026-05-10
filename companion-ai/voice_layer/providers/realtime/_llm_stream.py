"""Shared streaming LLM helper for realtime voice providers.

Extracted from ``local_realtime.py`` so that any realtime provider (local,
cloud, volc, …) can reuse the same OpenAI-compatible streaming path.

The helper reads runtime LLM config (set by the frontend Settings drawer)
and falls back to environment-level settings if the runtime override is
empty. It yields plain string tokens, sentence segmentation is left to the
caller.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

import httpx
import structlog

from shared_runtime.config import get_settings
from shared_runtime.llm_client import get_runtime_llm_config

logger = structlog.get_logger("voice_layer.providers.realtime._llm_stream")

DEFAULT_SYSTEM_PROMPT = (
    "你是一个温柔体贴、富有共情力的 AI 陪伴助手。"
    "用户正在通过语音和你对话，请用自然、口语化的中文短句回复，"
    "每次回复控制在 1-3 句话以内，避免书面语和列表格式。"
)


def _extract_openai_delta(data: str, *, model: str) -> str | None:
    try:
        obj = json.loads(data)
    except Exception:
        return None

    err = obj.get("error")
    if err:
        if isinstance(err, dict):
            msg = err.get("message") or err.get("code") or str(err)
        else:
            msg = str(err)
        raise RuntimeError(f"LLM stream error: {msg}")

    choices = obj.get("choices") or []
    if not choices:
        logger.debug(
            "realtime_llm.empty_choices_chunk",
            model=model,
            keys=list(obj.keys()),
        )
        return None

    delta = (choices[0] or {}).get("delta") or {}
    token = delta.get("content")
    return token if isinstance(token, str) else None


async def stream_llm(
    history: list[dict[str, str]],
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    temperature: float = 0.7,
    max_tokens: int = 512,
    timeout: float = 60.0,
    first_token_timeout: float = 15.0,
) -> AsyncIterator[str]:
    """Stream tokens from an OpenAI-compatible chat completions endpoint.

    Yields plain content chunks (not full deltas). Raises ``RuntimeError``
    on non-2xx responses with the upstream body trimmed to 500 chars so
    the caller can surface a useful error.

    If the LLM produces no tokens within ``first_token_timeout`` seconds
    the generator yields a fallback apology message so the frontend
    doesn't stay stuck in "thinking" indefinitely.
    """
    settings = get_settings()
    rt = get_runtime_llm_config()

    api_key = rt.get("openai_api_key") or settings.openai_api_key
    base_url = (
        rt.get("openai_base_url") or settings.openai_base_url or "https://api.openai.com/v1"
    ).rstrip("/")
    model = rt.get("default_model") or settings.default_llm_model or "qwen-turbo"

    if not api_key:
        yield "（语音模型已就绪，但还没有配置 LLM 接口。请在设置中填入大模型 API Key。）"
        return

    messages = [{"role": "system", "content": system_prompt}] + history
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{base_url}/chat/completions"

    logger.debug("realtime_llm.request", model=model, base_url=base_url[:60])

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                err_body = await resp.aread()
                snippet = err_body.decode("utf-8", errors="ignore")[:500]
                raise RuntimeError(f"LLM HTTP {resp.status_code}: {snippet}")

            # -----------------------------------------------------------------
            # Wrap aiter_lines() with a first-token timeout.
            #
            # Strategy: create a "next line" task that races against a timer.
            # If the timer wins (no line within first_token_timeout), yield a
            # fallback message.  After the first token-containing line arrives
            # we switch to direct passthrough — no more timeout checks.
            # -----------------------------------------------------------------
            lines = resp.aiter_lines()
            deadline = asyncio.get_running_loop().time() + first_token_timeout
            first_token_seen = False

            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    logger.warning("realtime_llm.first_token_timeout", model=model)
                    yield "（抱歉，小暖还在反应中，请稍后再试...）"
                    return

                next_line_task = asyncio.create_task(lines.__anext__())
                try:
                    line = await asyncio.wait_for(next_line_task, timeout=min(remaining, 2.0))
                except asyncio.TimeoutError:
                    continue  # poll cycle, still within deadline
                except StopAsyncIteration:
                    return
                except Exception:
                    next_line_task.cancel()
                    with contextlib.suppress(Exception):
                        await next_line_task
                    return

                # We have a line — parse it
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                token = _extract_openai_delta(data, model=model)
                if token:
                    first_token_seen = True
                    logger.debug("realtime_llm.first_token")
                    yield token
                    break  # exit the timed loop

            # -----------------------------------------------------------------
            # Passthrough: first token arrived, stream remaining lines without
            # any timeout overhead.
            # -----------------------------------------------------------------
            if first_token_seen:
                async for line in lines:
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    token = _extract_openai_delta(data, model=model)
                    if token:
                        yield token


__all__ = ["stream_llm", "DEFAULT_SYSTEM_PROMPT"]
