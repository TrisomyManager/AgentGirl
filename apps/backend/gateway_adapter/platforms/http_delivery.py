"""Bounded HTTP replies and honest uncertainty for mutating platform requests."""

import asyncio
import math
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class HTTPDelivery:
    outcome: str
    data: dict[str, Any] | None = None
    status: int | None = None
    retry_after: float | None = None


def valid_text(value, limit):
    if not isinstance(value, str) or not value:
        return False
    try:
        value.encode("utf-8")
        return len(value.encode("utf-16-le")) // 2 <= limit
    except UnicodeError:
        return False


async def request_json(client, method, url, *, max_bytes=65536, total_timeout=35, **kwargs):
    """Never retry a potentially committed send, or expose provider diagnostics."""
    try:
        async with asyncio.timeout(total_timeout):
            return await _request_json(client, method, url, max_bytes=max_bytes, **kwargs)
    except (httpx.HTTPError, TimeoutError):
        return HTTPDelivery("unknown")


async def _request_json(client, method, url, *, max_bytes, **kwargs):
    try:
        async with client.stream(method, url, **kwargs) as response:
            status = response.status_code
            if not 200 <= status < 300:
                retry_after = None
                if status == 429:
                    try:
                        value = float(response.headers.get("retry-after", "30"))
                        retry_after = min(300, max(1, value)) if math.isfinite(value) else 30
                    except (TypeError, ValueError, OverflowError):
                        retry_after = 30
                return HTTPDelivery(
                    "rejected" if 400 <= status < 500 else "unknown", status=status, retry_after=retry_after
                )
            body = bytearray()
            async for block in response.aiter_bytes():
                if len(body) + len(block) > max_bytes:
                    return HTTPDelivery("unknown", status=status)
                body.extend(block)
            try:
                import json

                data = json.loads(body)
            except (ValueError, UnicodeDecodeError, RecursionError):
                return HTTPDelivery("unknown", status=status)
            if not isinstance(data, dict):
                return HTTPDelivery("unknown", status=status)
            return HTTPDelivery("response", data, status)
    except httpx.HTTPError:
        return HTTPDelivery("unknown")
