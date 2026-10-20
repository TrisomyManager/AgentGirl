"""Host-injected content decisions. Standalone voice has no business-policy imports."""

import asyncio
import inspect
from contextlib import aclosing
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckedText:
    text: str
    blocked: bool = False
    category: str = "general"


_review = None
_stream = None
_complete_output = None


def set_text_policy(review=None, stream=None, *, complete_output=None):
    global _review, _stream, _complete_output
    _review, _stream = review, stream
    _complete_output = complete_output


def policy_enabled():
    return _review is not None


def requires_complete_output():
    # Unknown host policies may depend on a future suffix.
    return bool(_complete_output()) if _complete_output else policy_enabled()


async def check_text(text, *, source):
    review = _review
    if review is None:
        return CheckedText(text)
    try:
        async with asyncio.timeout(3):
            result = review(text, source=source)
            if inspect.isawaitable(result):
                result = await result
        if not isinstance(result, CheckedText):
            raise TypeError("Invalid text policy decision")
        return result
    except Exception:
        return CheckedText("这段内容暂时无法完成检查，请稍后再试。", True, "review_unavailable")


async def checked_tokens(source, *, on_block=None):
    factory = _stream
    target = factory(source, on_block=on_block) if factory else source
    async with aclosing(target):
        async for token in target:
            yield token


async def literal_text(text):
    yield text
