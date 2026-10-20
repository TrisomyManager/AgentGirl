"""Working memory: per-session rolling context + live structured summary.

Context
-------
Companion-AI's long-term store (``memory_system/recall.py`` +
``vector_store.py`` + Neo4j graph) is great at "5 weeks ago you said you
have a cat named Mimi" but bad at "the user just told you, two messages
ago, that they're stressed". The chat experience needs both layers:

  - **Working memory** (this module): the rolling K most recent turns
    of the active session plus a structured live summary that the
    prompt builder can inject without having to dump raw turn text.
    Lives in Redis when available, falls back to in-memory dict in
    Lite Mode (which is what ``InMemoryShortTermMemory`` already
    does for ``short_term.py``).
  - **Persistent memory**: vector + graph + relationship metrics, for
    long-running facts and emotional trends.

Working memory is *not* a replacement for ``ShortTermMemory``: that
module stores raw conversational turns keyed by ``session_id``. This
module sits one layer above and exposes a model-shaped object
(``WorkingMemoryState``) tuned for direct prompt injection.

Public surface
--------------

- ``WorkingMemory.observe_turn(...)`` — call this once per finished
  turn (used by ``node_sync_memory``); it appends a turn record and
  refreshes the live summary.
- ``WorkingMemory.snapshot(session_id)`` — returns the
  ``WorkingMemoryState`` to be merged into ``MemoryRecallResult`` /
  the system prompt at the start of the next turn.
- ``WorkingMemory.clear(session_id)`` — wipe a session's working
  memory; called when the user clicks 清空对话 in the UI.

Behaviour rules
---------------

  1. Rolling buffer keeps the last ``window_size`` turns (default 6).
  2. Live summary is rebuilt on every ``observe_turn`` / ``snapshot`` rebuild:

     - latest user emotion tag (if available)
     - dominant topic — bag-of-words pick stored as ``dominant_topic_heuristic``
     - optional LLM enrichment (``COMPANION_WORKING_MEMORY_LLM_SUMMARY`` /
       ``COMPANION_WORKING_MEMORY_LLM_DIGEST``): one batched JSON call can set
       ``dominant_topic`` and/or ``session_digest``; results are cached per
       session for ``COMPANION_WORKING_MEMORY_SUMMARY_TTL_SECONDS`` when the
       in-window transcript fingerprint is unchanged (avoids duplicate calls
       on rapid ``recall_memory`` / ``snapshot``).
     - regex facts: name / role / likes / dislikes (same patterns as before)
     - last assistant reply preview (first 60 chars)

  Without the LLM flags (default) there is **no** extra network call.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import structlog

from memory_system.short_term import short_term_memory
from shared_runtime.config import get_settings

logger = structlog.get_logger("memory_system.working")


_NAME_PATTERN = re.compile(r"我叫([\w\u4e00-\u9fff·]{1,20})")
_PREFERENCE_PATTERN = re.compile(r"我(?:很|最)?喜欢([^，。！？!?\n]{1,30})")
_DISLIKE_PATTERN = re.compile(r"我(?:很|最)?讨厌([^，。！？!?\n]{1,30})")
_ROLE_PATTERN = re.compile(r"我是(?:一个|一名)?([\u4e00-\u9fff]{2,12})")

_TOPIC_STOPWORDS = {
    "我",
    "你",
    "他",
    "她",
    "它",
    "我们",
    "你们",
    "他们",
    "是",
    "的",
    "了",
    "吗",
    "呢",
    "吧",
    "啊",
    "呀",
    "哈",
    "哦",
    "今天",
    "现在",
    "一下",
    "一些",
    "一点",
    "什么",
    "有点",
    "可以",
    "应该",
    "好像",
    "感觉",
    "觉得",
    "知道",
    "想要",
    "喜欢",
}


@dataclass
class WorkingMemoryTurn:
    """One conversational turn captured into working memory."""

    turn_id: str
    user_message: str
    assistant_message: str
    emotion: Optional[str] = None
    intent: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass
class WorkingMemoryState:
    """Structured snapshot of a single session's working memory."""

    session_id: str
    turns: List[WorkingMemoryTurn] = field(default_factory=list)
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    likes: List[str] = field(default_factory=list)
    dislikes: List[str] = field(default_factory=list)
    dominant_topic: Optional[str] = None
    dominant_topic_heuristic: Optional[str] = None
    session_digest: Optional[str] = None
    history_digest: Optional[str] = None
    last_user_emotion: Optional[str] = None
    last_assistant_preview: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_count": len(self.turns),
            "user_name": self.user_name,
            "user_role": self.user_role,
            "likes": list(self.likes),
            "dislikes": list(self.dislikes),
            "dominant_topic": self.dominant_topic,
            "dominant_topic_heuristic": self.dominant_topic_heuristic,
            "session_digest": self.session_digest,
            "history_digest": self.history_digest,
            "last_user_emotion": self.last_user_emotion,
            "last_assistant_preview": self.last_assistant_preview,
            "turns": [
                {
                    "turn_id": t.turn_id,
                    "user_message": t.user_message,
                    "assistant_message": t.assistant_message,
                    "emotion": t.emotion,
                    "intent": t.intent,
                    "timestamp": t.timestamp,
                }
                for t in self.turns
            ],
        }


class WorkingMemory:
    """Per-session rolling buffer + live structured summary."""

    def __init__(self, window_size: int = 6) -> None:
        self.window_size = window_size
        self._states: Dict[str, WorkingMemoryState] = {}
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._short_term = short_term_memory
        # session_id -> {fingerprint, topic, digest, monotonic_ts}
        self._llm_cache: Dict[str, Dict[str, Any]] = {}

    async def observe_turn(
        self,
        session_id: str,
        turn_id: str,
        user_message: str,
        assistant_message: str,
        emotion: Optional[str] = None,
        intent: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> WorkingMemoryState:
        """Record a turn and refresh the live summary for this session."""
        try:
            await self._short_term.add_turn(
                session_id=session_id,
                turn_id=turn_id,
                user_message=user_message,
                assistant_message=assistant_message,
                emotion=None,
                metadata={**(metadata or {}), "intent": intent, "emotion": emotion, "user_id": user_id},
            )
        except Exception as exc:
            logger.warning("working_memory.short_term_write_failed", error=str(exc))

        async with self._session_locks.setdefault(session_id, asyncio.Lock()):
            state = await self._rebuild_state(session_id)
            from shared_runtime.user_lifecycle import assert_user_context
            assert_user_context()
            self._states[session_id] = state
        logger.info(
            "working_memory.observed",
            session_id=session_id,
            turns=len(state.turns),
            topic=state.dominant_topic,
        )
        return state

    async def snapshot(self, session_id: str) -> WorkingMemoryState:
        async with self._session_locks.setdefault(session_id, asyncio.Lock()):
            state = self._states.get(session_id)
            if state is None:
                state = await self._rebuild_state(session_id)
                self._states[session_id] = state
            return state

    async def clear(self, session_id: str) -> None:
        async with self._session_locks.setdefault(session_id, asyncio.Lock()):
            self._states.pop(session_id, None)
            self._llm_cache.pop(session_id, None)
        try:
            await self._short_term.clear_session(session_id)
        except Exception as exc:
            logger.warning("working_memory.clear_failed", error=str(exc))

    async def invalidate(self, session_id: str) -> None:
        """Discard computed context after an atomic database deletion, without deleting new turns."""
        async with self._session_locks.setdefault(session_id, asyncio.Lock()):
            self._states.pop(session_id, None)
            self._llm_cache.pop(session_id, None)

    async def _rebuild_state(self, session_id: str) -> WorkingMemoryState:
        try:
            raw_turns = await self._short_term.get_session_turns(session_id)
        except Exception as exc:
            logger.warning("working_memory.short_term_read_failed", session_id=session_id, error=str(exc))
            raw_turns = []

        windowed = raw_turns[-self.window_size :]
        turns: List[WorkingMemoryTurn] = []
        for raw in windowed:
            metadata = raw.get("metadata") or {}
            turns.append(
                WorkingMemoryTurn(
                    turn_id=raw.get("turn_id", ""),
                    user_message=raw.get("user_message", "") or "",
                    assistant_message=raw.get("assistant_message", "") or "",
                    emotion=metadata.get("emotion") or raw.get("emotion"),
                    intent=metadata.get("intent"),
                    timestamp=raw.get("timestamp"),
                )
            )

        state = WorkingMemoryState(session_id=session_id, turns=turns)
        await self._compact_history(session_id, raw_turns, state)

        if turns:
            last = turns[-1]
            state.last_user_emotion = last.emotion
            state.last_assistant_preview = last.assistant_message[:60] + (
                "…" if len(last.assistant_message) > 60 else ""
            )

        for t in turns:
            msg = t.user_message
            if m := _NAME_PATTERN.search(msg):
                state.user_name = m.group(1).strip()
            if m := _ROLE_PATTERN.search(msg):
                state.user_role = m.group(1).strip()
            if m := _PREFERENCE_PATTERN.search(msg):
                like = m.group(1).strip()
                if like and like not in state.likes:
                    state.likes.append(like)
            if m := _DISLIKE_PATTERN.search(msg):
                dislike = m.group(1).strip()
                if dislike and dislike not in state.dislikes:
                    state.dislikes.append(dislike)

        state.dominant_topic_heuristic = self._infer_topic(turns)
        state.dominant_topic = state.dominant_topic_heuristic
        await self._maybe_llm_enrich(state)
        return state

    async def _compact_history(
        self, session_id: str, raw_turns: List[Dict[str, Any]], state: WorkingMemoryState
    ) -> None:
        """Preserve evicted context and user facts without expanding the raw prompt window."""
        saved = await self._short_term.load_digest(session_id)
        older = raw_turns[: -self.window_size]
        covered = saved.get("covered_turn_id")
        if covered and any(t.get("turn_id") == covered for t in older):
            index = next(i for i, t in enumerate(older) if t.get("turn_id") == covered)
            pending = older[index + 1 :]
        elif saved.get("last_seq"):
            pending = [t for t in older if t.get("storage_seq", 0) > saved["last_seq"]]
        else:
            pending = older

        if pending:
            previous = saved.get("digest", "")
            transcript = "\n".join(
                f"用户：{t.get('user_message', '')[:400]}\n助手：{t.get('assistant_message', '')[:200]}"
                for t in pending
            )
            digest = (previous + "\n" + transcript).strip()[-2000:]
            settings = get_settings()
            saved["pending_compression_turns"] = saved.get("pending_compression_turns", 0) + len(pending)
            use_model = getattr(settings, "working_memory_compression_use_llm", False) or getattr(
                settings, "working_memory_llm_digest", False
            )
            batch_size = getattr(settings, "working_memory_compression_batch_turns", 3)
            if (
                use_model
                and saved["pending_compression_turns"] >= batch_size
                and time.time() - saved.get("last_summary_attempt_epoch", 0) >= 45
            ):
                from shared_runtime.llm_client import LLMClient

                llm = LLMClient()
                if llm.has_configured_provider():
                    saved["last_summary_attempt_epoch"] = time.time()
                    try:
                        result = await asyncio.wait_for(
                            llm.generate(
                                system_prompt="将已有摘要与新增对话合并为简洁的连续摘要。保留用户的事实、约定、未解决事项与情绪变化。不要把助手猜测当成用户事实。只输出摘要。",
                                user_message=f"已有摘要：{previous[:2000]}\n新增对话：\n{transcript[:6000]}",
                                model=settings.working_memory_summary_model,
                                temperature=0.2,
                                max_tokens=600,
                            ),
                            timeout=4.0,
                        )
                        candidate = (result.get("assistant_message") or "").strip()
                        if candidate:
                            digest = candidate[:2000]
                            saved["pending_compression_turns"] = 0
                    except Exception as exc:
                        logger.warning("working_memory.compaction_fallback", error=type(exc).__name__)
                    finally:
                        if closer := getattr(llm, "close", None):
                            await closer()

            for turn in pending:
                message = turn.get("user_message", "")
                if match := _NAME_PATTERN.search(message):
                    saved["user_name"] = match.group(1).strip()
                if match := _ROLE_PATTERN.search(message):
                    saved["user_role"] = match.group(1).strip()
                for pattern, key in ((_PREFERENCE_PATTERN, "likes"), (_DISLIKE_PATTERN, "dislikes")):
                    if match := pattern.search(message):
                        saved[key] = list(dict.fromkeys(saved.get(key, []) + [match.group(1).strip()]))[-20:]
            saved.update(digest=digest, covered_turn_id=pending[-1]["turn_id"], last_seq=pending[-1].get("storage_seq"))
            await self._short_term.save_digest(session_id, saved)

        state.history_digest = saved.get("digest")
        state.user_name = saved.get("user_name")
        state.user_role = saved.get("user_role")
        state.likes = list(saved.get("likes", []))
        state.dislikes = list(saved.get("dislikes", []))

    @staticmethod
    def _transcript_fingerprint(turns: List[WorkingMemoryTurn]) -> str:
        parts: List[str] = []
        for t in turns[-6:]:
            parts.append(f"{t.turn_id}|{t.user_message}|{t.assistant_message}")
        return "\n".join(parts)

    def _cache_get(self, session_id: str, fingerprint: str) -> Optional[Dict[str, Any]]:
        entry = self._llm_cache.get(session_id)
        if not entry or entry.get("fingerprint") != fingerprint:
            return None
        ttl = get_settings().working_memory_summary_ttl_seconds
        if time.monotonic() - float(entry.get("ts", 0)) > ttl:
            return None
        return entry

    def _cache_set(
        self,
        session_id: str,
        fingerprint: str,
        topic: Optional[str],
        digest: Optional[str],
    ) -> None:
        self._llm_cache[session_id] = {
            "fingerprint": fingerprint,
            "topic": topic,
            "digest": digest,
            "ts": time.monotonic(),
        }

    async def _maybe_llm_enrich(self, state: WorkingMemoryState) -> None:
        settings = get_settings()
        want_topic = settings.working_memory_llm_summary
        want_digest = settings.working_memory_llm_digest
        if not (want_topic or want_digest):
            return
        if not state.turns:
            return

        try:
            from shared_runtime.llm_client import LLMClient
        except Exception as exc:
            logger.warning("working_memory.llm_import_failed", error=str(exc))
            return

        llm = LLMClient()
        if not llm.has_configured_provider():
            return

        lines: List[str] = []
        for t in state.turns[-6:]:
            u = (t.user_message or "").strip().replace("\n", " ")
            if u:
                lines.append(f"用户：{u[:200]}")
            a = (t.assistant_message or "").strip().replace("\n", " ")
            if a:
                lines.append(f"助手：{a[:120]}")
        if not lines:
            return

        fingerprint = self._transcript_fingerprint(state.turns)
        cached = self._cache_get(state.session_id, fingerprint)
        if cached is not None:
            if want_topic and cached.get("topic"):
                state.dominant_topic = str(cached["topic"])[:24]
            if want_digest and cached.get("digest"):
                state.session_digest = str(cached["digest"])[:200]
            logger.debug("working_memory.llm_cache_hit", session_id=state.session_id)
            return

        transcript = "\n".join(lines)
        heuristic = state.dominant_topic_heuristic or ""
        sys = (
            "你是对话分析助手。根据最近几轮用户与助手的中文对话，输出严格 JSON，不要其它文字。"
            "字段：topic（字符串，2到12个汉字概括用户最关心的话题；无则 null），"
            "digest（字符串，一句中文≤60字概括当前对话在聊什么、用户情绪或诉求；无则 null）。"
        )
        user = (
            f"启发式候选主题（可能不准）：{heuristic or '无'}\n\n"
            f"对话摘录：\n{transcript}\n\n"
            '只输出形如 {"topic":"考试压力","digest":"用户在倾诉备考焦虑，希望得到陪伴"} 的 JSON。'
        )
        model = settings.working_memory_summary_model
        topic_out: Optional[str] = None
        digest_out: Optional[str] = None
        try:
            out = await llm.generate(
                system_prompt=sys,
                user_message=user,
                model=model,
                temperature=0.2,
                max_tokens=200,
            )
            raw = (out.get("assistant_message") or "").strip()
            topic_out, digest_out = self._parse_working_memory_llm_json(raw)
        except Exception as exc:
            logger.warning("working_memory.llm_enrich_failed", error=str(exc))
            return
        finally:
            if closer := getattr(llm, "close", None):
                await closer()

        self._cache_set(state.session_id, fingerprint, topic_out, digest_out)

        if want_topic and topic_out:
            state.dominant_topic = topic_out[:24]
        if want_digest and digest_out:
            state.session_digest = digest_out[:200]
        logger.info(
            "working_memory.llm_enrich_applied",
            session_id=state.session_id,
            has_topic=bool(topic_out),
            has_digest=bool(digest_out),
        )

    @staticmethod
    def _parse_working_memory_llm_json(raw: str) -> Tuple[Optional[str], Optional[str]]:
        text = raw.strip()
        if "```" in text:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
            if m:
                text = m.group(1).strip()
        data: Any
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            brace = re.search(r"\{[^{}]*\}", text)
            if not brace:
                return None, None
            try:
                data = json.loads(brace.group(0))
            except json.JSONDecodeError:
                return None, None
        if not isinstance(data, dict):
            return None, None

        def _norm_str(val: Any) -> Optional[str]:
            if val is None:
                return None
            if isinstance(val, str):
                s = val.strip()
                if not s or s.lower() == "null":
                    return None
                return s
            return None

        return _norm_str(data.get("topic")), _norm_str(data.get("digest"))

    @staticmethod
    def _infer_topic(turns: List[WorkingMemoryTurn]) -> Optional[str]:
        if not turns:
            return None
        counter: Counter[str] = Counter()
        for t in turns:
            text = t.user_message
            for cjk_run in re.findall(r"[\u4e00-\u9fff]+", text):
                if len(cjk_run) < 2:
                    continue
                for i in range(len(cjk_run) - 1):
                    bigram = cjk_run[i : i + 2]
                    if bigram in _TOPIC_STOPWORDS:
                        continue
                    counter[bigram] += 1
            for token in re.findall(r"[A-Za-z]{3,}", text):
                if token.lower() in _TOPIC_STOPWORDS:
                    continue
                counter[token] += 1
        if not counter:
            return None
        _topic, count = counter.most_common(1)[0]
        if count < 2:
            return None
        return _topic


_working_memory: Optional[WorkingMemory] = None


def get_working_memory() -> WorkingMemory:
    global _working_memory
    if _working_memory is None:
        _ = get_settings()
        _working_memory = WorkingMemory(window_size=6)
    return _working_memory
