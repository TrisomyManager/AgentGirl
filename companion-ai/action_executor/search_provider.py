"""Search provider abstraction + no-key DuckDuckGo fallback.

Priority:
  1. If a custom search API key is configured, a future provider can use it.
  2. Otherwise fall back to DuckDuckGo Instant Answer API (no key required).

All provider implementations are async and return a uniform ``SearchResult``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger("action_executor.search_provider")


@dataclass
class SearchResult:
    """Uniform return shape from any search provider."""

    query: str
    results: List[Dict[str, Any]] = field(default_factory=list)
    answer: Optional[str] = None
    source: str = "unknown"
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and (bool(self.results) or bool(self.answer))

    def to_text(self) -> str:
        """Format results into a short human-readable string."""
        parts: List[str] = []
        if self.answer:
            parts.append(self.answer)
        for r in self.results[:3]:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            href = r.get("url", "")
            line = f"{title} — {snippet}".strip(" —")
            if href:
                line += f" ({href})"
            parts.append(line)
        if not parts:
            return "暂无搜索结果。"
        return "\n".join(parts)


class SearchProvider(ABC):
    """Abstract base for search backends."""

    @abstractmethod
    async def search(self, query: str) -> SearchResult:
        ...


class DuckDuckGoSearchProvider(SearchProvider):
    """DuckDuckGo Instant Answer API — no API key required.

    Uses the HTML endpoint and extracts an abstract / related topics.
    This is intentionally simple; for production workloads with an API
    key, a Bing/Google provider would supersede it.
    """

    async def search(self, query: str) -> SearchResult:
        if not query or not query.strip():
            return SearchResult(query=query or "", error="empty_query")

        try:
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                # DuckDuckGo Instant Answer API (no key needed)
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query.strip(),
                        "format": "json",
                        "no_html": "1",
                        "skip_disambig": "1",
                    },
                    headers={"User-Agent": "companion-ai/1.0"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("search.duckduckgo_failed", query=query[:50], error=str(exc))
            return SearchResult(
                query=query,
                error=f"搜索请求失败：{exc}",
                source="duckduckgo",
            )

        abstract_text = data.get("AbstractText", "")
        abstract_url = data.get("AbstractURL", "")
        related = data.get("RelatedTopics", []) or []

        results: List[Dict[str, Any]] = []
        if abstract_text:
            results.append(
                {
                    "title": data.get("Heading", ""),
                    "snippet": abstract_text,
                    "url": abstract_url,
                }
            )

        for topic in related[:5]:
            if "Result" in topic:
                text = topic.get("Text", "")
                href = topic.get("FirstURL", "")
                if text:
                    results.append({"title": "", "snippet": text, "url": href})
            elif "Topics" in topic:
                for sub in topic["Topics"][:3]:
                    text = sub.get("Text", "")
                    href = sub.get("FirstURL", "")
                    if text:
                        results.append({"title": "", "snippet": text, "url": href})

        return SearchResult(
            query=query,
            results=results,
            answer=abstract_text or None,
            source="duckduckgo",
        )


_provider: Optional[SearchProvider] = None


def get_search_provider() -> SearchProvider:
    """Return a process-level search provider singleton.

    Currently always returns DuckDuckGo (no key).  When a paid provider
    is configured via Settings, this factory can branch accordingly.
    """
    global _provider
    if _provider is None:
        _provider = DuckDuckGoSearchProvider()
    return _provider


def set_search_provider(provider: SearchProvider) -> None:
    """Override the global provider (useful in tests)."""
    global _provider
    _provider = provider
