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
  2. Live summary is rebuilt on every ``observe_turn``:

     - latest user emotion tag (if available)
     - dominant topic — bag-of-words pick over recent turns, stored as
       ``dominant_topic_heuristic``; when ``COMPANION_WORKING_MEMORY_LLM_SUMMARY=true``
       and an LLM key is configured, a tiny completion may replace
       ``dominant_topic`` with a clearer short label (JSON ``{"topic":"..."}``).
     - any "我叫X / 我喜欢X" facts surfaced via the same regexes
       state_machine already uses (``_NAME_PATTERN`` / ``_PREFERENCE_PATTERN``)
     - last assistant reply preview (first 60 chars)

  Without the LLM flag (default) there is **no** extra network call — the
  path stays deterministic and Lite-Mode friendly.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

from memory_system.short_term import short_term_memory
from shared.config import get_settings

logger = structlog.get_logger("memory_system.working")


_NAME_PATTERN = re.compile(r"我叫([\w\u4e00-\u9fff·]{1,20})")
_PREFERENCE_PATTERN = re.compile(r"我(?:很|最)?喜欢([^，。！？!?\n]{1,30})")
_DISLIKE_PATTERN = re.compile(r"我(?:很|最)?讨厌([^，。！？!?\n]{1,30})")
_ROLE_PATTERN = re.compile(r"我是(?:一个|一名)?([\u4e00-\u9fff]{2,12})")

# Words that are mostly noise when picking a "dominant topic" — short
# pronouns / particles / filler tokens.
_TOPIC_STOPWORDS = {
    "我", "你", "他", "她", "它", "我们", "你们", "他们",
    "是", "的", "了", "吗", "呢", "吧", "啊", "呀", "哈", "哦",
    "今天", "现在", "一下", "一些", "一点", "什么", "有点",
    "可以", "应该", "好像", "感觉", "觉得", "知道", "想要", "喜欢",
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
    """Structured snapshot of a single session's working memory.

    The fields are deliberately small and serialisable so the orchestrator
    can stash this directly inside ``MemoryRecallResult.working_memory``
    and the prompt builder can render it under a 【当前对话状态】 section.
    """

    session_id: str
    turns: List[WorkingMemoryTurn] = field(default_factory=list)
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    likes: List[str] = field(default_factory=list)
    dislikes: List[str] = field(default_factory=list)
    dominant_topic: Optional[str] = None
    dominant_topic_heuristic: Optional[str] = None
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
    """Per-session rolling buffer + live structured summary.

    Backed by ``ShortTermMemory`` (Redis or in-memory dict) for the raw
    turn buffer, but adds a Python-side structured summary that lives in
    process memory keyed by ``session_id``. The summary is cheap to
    rebuild from the raw buffer, so we recompute on every ``observe_turn``
    rather than persist it.
    """

    def __init__(self, window_size: int = 6) -> None:
        self.window_size = window_size
        # In-process structured summaries; rebuilt from short_term backend.
        self._states: Dict[str, WorkingMemoryState] = {}
        self._lock = asyncio.Lock()
        # Note: backed by short_term_memory which already handles
        # lite/Redis split internally.
        self._short_term = short_term_memory

    # ---------------------------------------------------------------- API

    async def observe_turn(
        self,
        session_id: str,
        turn_id: str,
        user_message: str,
        assistant_message: str,
        emotion: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> WorkingMemoryState:
        """Record a turn and refresh the live summary for this session."""
        try:
            await self._short_term.add_turn(
                session_id=session_id,
                turn_id=turn_id,
                user_message=user_message,
                assistant_message=assistant_message,
                emotion=None,  # short_term expects EmotionTag enum; keep raw str here only
                metadata={"intent": intent, "emotion": emotion},
            )
        except Exception as exc:
            logger.warning("working_memory.short_term_write_failed", error=str(exc))

        async with self._lock:
            state = await self._rebuild_state(session_id)
            self._states[session_id] = state
        logger.info(
            "working_memory.observed",
            session_id=session_id,
            turns=len(state.turns),
            topic=state.dominant_topic,
        )
        return state

    async def snapshot(self, session_id: str) -> WorkingMemoryState:
        """Return the current working memory state for a session.

        If the in-process summary cache is empty (e.g. fresh process or
        after restart) this rebuilds it from the underlying short-term
        backend so reload-resilience is not lost.
        """
        async with self._lock:
            state = self._states.get(session_id)
            if state is None:
                state = await self._rebuild_state(session_id)
                self._states[session_id] = state
            return state

    async def clear(self, session_id: str) -> None:
        async with self._lock:
            self._states.pop(session_id, None)
        try:
            await self._short_term.clear_session(session_id)
        except Exception as exc:
            logger.warning("working_memory.clear_failed", error=str(exc))

    # ----------------------------------------------------------- internals

    async def _rebuild_state(self, session_id: str) -> WorkingMemoryState:
        try:
            raw_turns = await self._short_term.get_session_turns(session_id)
        except Exception as exc:
            logger.warning(
                "working_memory.short_term_read_failed", session_id=session_id, error=str(exc)
            )
            raw_turns = []

        # ShortTermMemory returns oldest→newest; trim to window.
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

        if turns:
            last = turns[-1]
            state.last_user_emotion = last.emotion
            state.last_assistant_preview = (
                last.assistant_message[:60] + ("…" if len(last.assistant_message) > 60 else "")
            )

        # Heuristic facts pulled across the whole window so a name said
        # in turn 1 still survives at turn 5.
        for t in turns:
            msg = t.user_message
            if (m := _NAME_PATTERN.search(msg)) and not state.user_name:
                state.user_name = m.group(1).strip()
            if (m := _ROLE_PATTERN.search(msg)) and not state.user_role:
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
        await self._maybe_refine_topic_with_llm(state)
        return state

    @staticmethod
    def _infer_topic(turns: List[WorkingMemoryTurn]) -> Optional[str]:
        """Cheap bag-of-words topic pick over user messages.

        Chinese is segmentation-free, so we use a sliding 2-char window
        over each contiguous run of CJK ideographs. This catches the
        intended head-tokens (考试, 工作) instead of greedy-matching the
        leading 2-4 characters of each sentence (which ends up always
        picking 我最近在 / 我有点累 etc.).
        """
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
        # Need at least 2 occurrences to call something a "topic"; otherwise
        # we'd pick a random bigram from a single short message.
        topic, count = counter.most_common(1)[0]
        if count < 2:
            return None
        return topic

    async def _maybe_refine_topic_with_llm(self, state: WorkingMemoryState) -> None:
        """Optionally replace ``dominant_topic`` with a short LLM label (config-gated)."""
        settings = get_settings()
        if not settings.working_memory_llm_summary:
            return
        if not state.turns:
            return

        try:
            from shared.llm_client import LLMClient
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

        transcript = "\n".join(lines)
        heuristic = state.dominant_topic_heuristic or ""
        sys = (
            "你是对话分析助手。根据最近几轮用户与助手的中文对话，输出严格 JSON，"
            "不要其它文字。字段：topic（字符串，2到12个汉字或常见英文词组，概括用户最关心的话题；"
            "若无明确主题填 null）。"
        )
        user = (
            f"启发式候选主题（可能不准）：{heuristic or '无'}\n\n"
            f"对话摘录：\n{transcript}\n\n"
            '只输出形如 {"topic":"考试压力"} 或 {"topic":null} 的 JSON。'
        )
        model = settings.working_memory_summary_model
        try:
            out = await llm.generate(
                system_prompt=sys,
                user_message=user,
                model=model,
                temperature=0.2,
                max_tokens=80,
            )
            raw = (out.get("assistant_message") or "").strip()
            topic = self._extract_topic_from_llm_json(raw)
        except Exception as exc:
            logger.warning("working_memory.llm_topic_failed", error=str(exc))
            return

        if topic:
            state.dominant_topic = topic[:24]
            logger.info(
                "working_memory.llm_topic_applied",
                topic=state.dominant_topic,
                heuristic=heuristic or None,
            )

    @staticmethod
    def _extract_topic_from_llm_json(raw: str) -> Optional[str]:
        """Parse ``topic`` from model output; tolerate markdown fences."""
        text = raw.strip()
        if "```" in text:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
            if m:
                text = m.group(1).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            brace = re.search(r"\{[^{}]*\}", text)
            if not brace:
                return None
            try:
                data = json.loads(brace.group(0))
            except json.JSONDecodeError:
                return None
        if not isinstance(data, dict):
            return None
        topic = data.get("topic")
        if topic is None:
            return None
        if not isinstance(topic, str):
            return None
        topic = topic.strip()
        if not topic or topic.lower() == "null":
            return None
        return topic


_working_memory: Optional[WorkingMemory] = None


def get_working_memory() -> WorkingMemory:
    """Process-wide singleton; window size taken from settings if exposed."""
    global _working_memory
    if _working_memory is None:
        # Settings doesn't currently carry a working_memory_window field,
        # so we default to 6. Adding a dedicated field is cheap and can
        # land alongside the next memory iteration.
        _ = get_settings()  # touch the settings cache for warm-up
        _working_memory = WorkingMemory(window_size=6)
    return _working_memory
