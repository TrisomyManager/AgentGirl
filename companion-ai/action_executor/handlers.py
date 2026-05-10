"""Built-in action handlers.

These are the built-in actions the companion can perform:

  - ``get_time``      — replies with the current local time.
  - ``get_weather``   — current conditions via Open-Meteo (no API key).
  - ``set_reminder``  — parses a natural-language delay ("3 分钟后")
                        plus a body ("提醒我喝水"), persists it, and
                        returns the reminder id.
  - ``list_reminders`` — returns the current pending reminders so the
                        chat can answer "我有什么待办的？".
  - ``cancel_reminder`` — flips the cancelled_at flag.
  - ``query_memory``   — recalls long-term + working memory for a user.
  - ``update_user_profile`` — updates user preferences / profile fields.
  - ``timer_countdown`` — creates a one-shot timer (countdown) entry.
  - ``web_search``     — searches the web via DuckDuckGo (no key) or
                         a configured paid provider.

Every handler is async and registered into the process-wide
``ActionRegistry`` at import time via ``ensure_builtins_registered``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog

from action_executor.registry import ActionResult, get_registry
from action_executor.reminders import (
    extract_reminder_body,
    get_reminders_store,
    parse_relative_delay,
    parse_repeat_interval,
)
from action_executor.search_provider import get_search_provider

logger = structlog.get_logger("action_executor.handlers")


def _now_local() -> datetime:
    return datetime.now()


# ---------------------------------------------------------------------------
# get_time
# ---------------------------------------------------------------------------


async def get_time(params: Dict[str, Any]) -> ActionResult:
    now = _now_local()
    formatted = now.strftime("%Y-%m-%d %H:%M:%S")
    weekday = "一二三四五六日"[now.weekday()]
    return ActionResult(
        ok=True,
        message=f"现在是 {formatted}（星期{weekday}）。",
        data={"timestamp": now.isoformat(), "weekday": weekday},
    )


# ---------------------------------------------------------------------------
# get_weather (Open-Meteo — no API key)
# ---------------------------------------------------------------------------


async def get_weather(params: Dict[str, Any]) -> ActionResult:
    """Current conditions via Open-Meteo (no API key).

    Optional ``COMPANION_WEATHER_API_KEY`` is reserved for a future paid
    provider; when unset we still answer with real public data.
    """
    from action_executor.weather_open_meteo import fetch_current_weather

    raw_loc = (params or {}).get("location") or ""
    ok, message, data = await fetch_current_weather(raw_loc or "本地")
    return ActionResult(ok=ok, message=message, data=data)


# ---------------------------------------------------------------------------
# set_reminder
# ---------------------------------------------------------------------------


async def set_reminder(params: Dict[str, Any]) -> ActionResult:
    """Create a reminder.

    Accepts either:
      - structured params: ``user_id``, ``text``, and either
        ``delay_seconds`` (int) or ``fire_at`` (ISO 8601 string).
      - natural-language params: ``user_id`` and ``raw_text``;
        we parse '3 分钟后 喝水' from the body.
    """
    user_id = params.get("user_id") or "anonymous"
    session_id = params.get("session_id")

    fire_at: datetime | None = None

    explicit_iso = params.get("fire_at")
    if isinstance(explicit_iso, str):
        try:
            parsed = datetime.fromisoformat(explicit_iso)
            fire_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return ActionResult(
                ok=False,
                message=f"提醒时间格式不对：{explicit_iso}",
                data={"error": "invalid_fire_at"},
            )

    delay_seconds = params.get("delay_seconds")
    if fire_at is None and isinstance(delay_seconds, (int, float)) and delay_seconds > 0:
        from datetime import timedelta

        fire_at = datetime.now(timezone.utc) + timedelta(seconds=int(delay_seconds))

    raw_text = (params.get("raw_text") or params.get("text") or "").strip()
    body = (params.get("text") or "").strip() or extract_reminder_body(raw_text)

    if fire_at is None:
        delay = parse_relative_delay(raw_text)
        if delay:
            from datetime import timedelta as _td  # noqa: F401 — keep at top-level for clarity

            fire_at = datetime.now(timezone.utc) + delay

    if fire_at is None:
        return ActionResult(
            ok=False,
            message="我没听懂要在什么时候提醒你，你可以说'3 分钟后提醒我喝水'。",
            data={"error": "no_fire_time"},
        )

    if not body:
        return ActionResult(
            ok=False,
            message="要提醒你什么呀？告诉我具体内容，我帮你记着。",
            data={"error": "empty_body"},
        )

    repeat_td = parse_repeat_interval(raw_text)
    repeat_seconds = (
        int(repeat_td.total_seconds())
        if repeat_td is not None and repeat_td.total_seconds() >= 60
        else None
    )

    reminder = await get_reminders_store().add(
        user_id=user_id,
        session_id=session_id,
        text=body,
        fire_at=fire_at,
        repeat_interval_seconds=repeat_seconds,
    )
    delta_sec = (reminder.fire_at - datetime.now(timezone.utc)).total_seconds()
    when_friendly = _format_relative(delta_sec)
    msg = f"好的，我会在 {when_friendly} 提醒你「{body}」。"
    if repeat_seconds:
        msg += f"之后每 {_format_repeat_label(repeat_seconds)} 重复一次；需要停掉时在待办里取消对应 id 即可。"
    return ActionResult(
        ok=True,
        message=msg,
        data={
            "reminder": reminder.to_dict(),
            "fire_in_seconds": int(max(0, delta_sec)),
            "repeat_interval_seconds": repeat_seconds,
        },
    )


def _format_repeat_label(seconds: int) -> str:
    s = max(60, int(seconds))
    if s % 86400 == 0:
        return f"{s // 86400} 天"
    if s % 3600 == 0:
        return f"{s // 3600} 小时"
    if s % 60 == 0:
        return f"{s // 60} 分钟"
    return f"{s} 秒"


def _format_relative(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{int(round(seconds))} 秒后"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(round(minutes))} 分钟后"
    hours = minutes / 60
    if hours < 24:
        return f"{int(round(hours))} 小时后"
    days = hours / 24
    return f"{int(round(days))} 天后"


# ---------------------------------------------------------------------------
# list_reminders
# ---------------------------------------------------------------------------


async def list_reminders(params: Dict[str, Any]) -> ActionResult:
    user_id = params.get("user_id") or "anonymous"
    pending = await get_reminders_store().list_for_user(user_id)
    if not pending:
        return ActionResult(ok=True, message="你目前没有待办提醒哦。", data={"reminders": []})
    lines: List[str] = []
    for r in pending[:5]:
        delta = (r.fire_at - datetime.now(timezone.utc)).total_seconds()
        lines.append(f"- {_format_relative(delta)}：{r.text}")
    body = "\n".join(lines)
    return ActionResult(
        ok=True,
        message=f"你目前有 {len(pending)} 条待办提醒：\n{body}",
        data={"reminders": [r.to_dict() for r in pending]},
    )


# ---------------------------------------------------------------------------
# cancel_reminder
# ---------------------------------------------------------------------------


async def cancel_reminder(params: Dict[str, Any]) -> ActionResult:
    reminder_id = params.get("id") or params.get("reminder_id")
    user_id = params.get("user_id")
    if not reminder_id:
        return ActionResult(
            ok=False,
            message="需要告诉我要取消哪一条提醒（reminder id）。",
            data={"error": "missing_id"},
        )
    ok = await get_reminders_store().cancel(reminder_id, user_id=user_id)
    if not ok:
        return ActionResult(
            ok=False,
            message="没找到这条待办，可能已经触发或被取消了。",
            data={"reminder_id": reminder_id, "cancelled": False},
        )
    return ActionResult(
        ok=True,
        message="好的，已经把这条提醒取消了。",
        data={"reminder_id": reminder_id, "cancelled": True},
    )


# ---------------------------------------------------------------------------
# query_memory
# ---------------------------------------------------------------------------

# Avoid cross-module import — call memory APIs via HTTP (same process in
# monolithic/lite mode, separate service in microservice mode).
_memory_api_base: Optional[str] = None


def _get_memory_api_base() -> str:
    global _memory_api_base
    if _memory_api_base is None:
        import os

        port = os.environ.get("COMPANION_PORT", "8000")
        _memory_api_base = f"http://localhost:{port}"
    return _memory_api_base


async def _call_memory_recall(user_id: str, query: str, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """POST /memory/recall — semantic recall."""
    try:
        timeout = httpx.Timeout(8.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{_get_memory_api_base()}/memory/recall",
                json={"user_id": user_id, "query": query, "session_id": session_id, "top_k": 5, "include_graph": False},
            )
            resp.raise_for_status()
            data = resp.json()
            entries = data.get("entries", [])
            return [{"content": e.get("content", str(e)), "importance": e.get("importance", 0.5)} for e in entries]
    except Exception as exc:
        logger.warning("query_memory.recall_http_failed", user_id=user_id, error=str(exc))
        return []


async def _call_memory_list(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """GET /memory/user/{user_id}/list — raw listing."""
    try:
        timeout = httpx.Timeout(8.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{_get_memory_api_base()}/memory/user/{user_id}/list",
                params={"limit": limit},
            )
            resp.raise_for_status()
            entries = resp.json()
            return [{"content": e.get("content", str(e)), "importance": e.get("importance", 0.5)} for e in entries]
    except Exception as exc:
        logger.warning("query_memory.list_http_failed", user_id=user_id, error=str(exc))
        return []


async def _call_working_memory(session_id: str) -> Optional[Dict[str, Any]]:
    """GET /memory/working/{session_id} — working memory snapshot."""
    try:
        timeout = httpx.Timeout(5.0, connect=2.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{_get_memory_api_base()}/memory/working/{session_id}")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("query_memory.working_http_failed", session_id=session_id, error=str(exc))
        return None


async def query_memory(params: Dict[str, Any]) -> ActionResult:
    """Recall a user's long-term memories + working memory snapshot.

    Calls memory_system via HTTP so action_executor does not need a
    direct (cross-module) import of memory_system internals.

    Parameters:
        user_id (str, required): target user.
        query (str, optional): semantic query string; empty = list recent.
        session_id (str, optional): for working memory lookup.
    """
    user_id = params.get("user_id")
    if not user_id:
        return ActionResult(
            ok=False,
            message="小暖需要知道你在问谁的记忆呢，告诉我 user_id 吧～",
            data={"error": "missing_user_id"},
        )

    query_text = (params.get("query") or params.get("q") or "").strip()

    try:
        long_term_entries: List[Dict[str, Any]] = []
        working_summary: Optional[Dict[str, Any]] = None

        # Long-term memory: try semantic recall when there's a query.
        if query_text:
            recalled = await _call_memory_recall(str(user_id), query_text, params.get("session_id"))
            long_term_entries = recalled

        # If no query or recall returned nothing, list recent memories.
        if not long_term_entries:
            long_term_entries = await _call_memory_list(str(user_id), limit=10)

        # Working memory: per-session rolling context.
        session_id = params.get("session_id")
        if session_id:
            wm_data = await _call_working_memory(str(session_id))
            if wm_data:
                working_summary = {
                    "session_id": wm_data.get("session_id"),
                    "turn_count": len(wm_data.get("turns", [])),
                    "user_name": wm_data.get("user_name"),
                    "dominant_topic": wm_data.get("dominant_topic"),
                    "session_digest": wm_data.get("session_digest"),
                    "last_user_emotion": wm_data.get("last_user_emotion"),
                }

        # Format into a warm, concise message.
        parts: List[str] = []
        if query_text:
            parts.append(f"关于「{query_text}」的记忆：")
        else:
            parts.append("这是小暖记得的和你有关的事：")

        if long_term_entries:
            for entry in long_term_entries[:5]:
                content = entry.get("content", str(entry))
                importance = entry.get("importance", 0.5)
                stars = "★" * int(importance * 5) + "☆" * (5 - int(importance * 5))
                parts.append(f"  • {content} [{stars}]")
        else:
            parts.append("  （还没有相关的长期记忆哦）")

        if working_summary:
            parts.append("\n最近的对话状态：")
            if working_summary.get("user_name"):
                parts.append(f"  • 你的名字：{working_summary['user_name']}")
            if working_summary.get("dominant_topic"):
                parts.append(f"  • 话题：{working_summary['dominant_topic']}")
            if working_summary.get("session_digest"):
                parts.append(f"  • 摘要：{working_summary['session_digest']}")
            if working_summary.get("last_user_emotion"):
                parts.append(f"  • 情绪：{working_summary['last_user_emotion']}")

        return ActionResult(
            ok=True,
            message="\n".join(parts),
            data={
                "long_term_count": len(long_term_entries),
                "working_memory": working_summary,
                "query": query_text,
            },
        )
    except Exception as exc:
        logger.exception("query_memory.unexpected_error", user_id=user_id, error=str(exc))
        return ActionResult(
            ok=False,
            message="小暖查记忆的时候遇到了小意外，再试一次好吗？",
            data={"error": "unexpected", "detail": str(exc)},
        )


# ---------------------------------------------------------------------------
# update_user_profile
# ---------------------------------------------------------------------------


async def update_user_profile(params: Dict[str, Any]) -> ActionResult:
    """Update a user's profile field (e.g. preference, display_name).

    Parameters:
        user_id (str, required): target user.
        field (str, required): field name — "name", "preference", "locale", etc.
        value (str, required): new value.
    """
    user_id = params.get("user_id")
    field = (params.get("field") or "").strip()
    value = params.get("value")

    if not user_id:
        return ActionResult(
            ok=False,
            message="告诉小暖你要更新谁的资料呀～",
            data={"error": "missing_user_id"},
        )
    if not field or value is None:
        return ActionResult(
            ok=False,
            message="需要告诉小暖要更新什么字段和值哦，比如 field=preference, value=喜欢喝茶。",
            data={"error": "missing_field_or_value"},
        )

    try:
        from user_profile import UserProfileSnapshot, get_default_store
    except Exception as exc:
        logger.warning("update_user_profile.import_failed", error=str(exc))
        return ActionResult(
            ok=False,
            message="用户画像模块暂时不可用，稍后再试试好吗？",
            data={"error": "profile_module_unavailable"},
        )

    try:
        store = get_default_store()

        # Special-case common fields.
        if field in ("name", "display_name"):
            snap = await store.get(str(user_id)) or UserProfileSnapshot(user_id=str(user_id))
            snap.display_name = str(value)
            await store.upsert(snap)
            return ActionResult(
                ok=True,
                message=f"记住啦，你叫 {value}～以后小暖就这么称呼你啦。",
                data={"field": "display_name", "value": value},
            )

        if field == "locale":
            snap = await store.get(str(user_id)) or UserProfileSnapshot(user_id=str(user_id))
            snap.locale = str(value)
            await store.upsert(snap)
            return ActionResult(
                ok=True,
                message=f"好的，语言设置已更新为 {value}。",
                data={"field": "locale", "value": value},
            )

        # Default: treat as a preference key-value pair.
        await store.merge_preferences(str(user_id), **{field: value})
        return ActionResult(
            ok=True,
            message=f"小暖记下啦，你的 {field} 是 {value}～",
            data={"field": field, "value": value},
        )
    except Exception as exc:
        logger.exception("update_user_profile.error", user_id=user_id, error=str(exc))
        return ActionResult(
            ok=False,
            message="更新资料时出了点小问题，等下再试一次好吗？",
            data={"error": "unexpected", "detail": str(exc)},
        )


# ---------------------------------------------------------------------------
# timer_countdown
# ---------------------------------------------------------------------------


async def timer_countdown(params: Dict[str, Any]) -> ActionResult:
    """Create a one-shot countdown timer (fires N seconds from now).

    Unlike ``set_reminder`` which expects a natural-language body,
    ``timer_countdown`` focuses on "start counting from now".

    Parameters:
        duration_seconds (int, optional): explicit seconds.
        raw_text (str, optional): e.g. "5 分钟后" — parsed for delay.
        user_id (str, optional): defaults to "anonymous".
        label (str, optional): human-readable label for the timer.
    """
    user_id = params.get("user_id") or "anonymous"
    session_id = params.get("session_id")
    label = (params.get("label") or "").strip()
    raw_text = (params.get("raw_text") or "").strip()

    fire_at: Optional[datetime] = None

    # 1. Explicit seconds.
    explicit_sec = params.get("duration_seconds")
    if isinstance(explicit_sec, (int, float)) and explicit_sec > 0:
        fire_at = datetime.now(timezone.utc) + timedelta(seconds=int(explicit_sec))

    # 2. Parse from raw_text (e.g. "5 分钟后").
    if fire_at is None and raw_text:
        delay = parse_relative_delay(raw_text)
        if delay:
            fire_at = datetime.now(timezone.utc) + delay

    if fire_at is None:
        return ActionResult(
            ok=False,
            message="小暖没听懂要计时多久，你可以说「5 分钟」或者传 duration_seconds 哦。",
            data={"error": "no_duration"},
        )

    # Build a label if none provided.
    delta_sec = (fire_at - datetime.now(timezone.utc)).total_seconds()
    if not label:
        if raw_text:
            label = f"倒计时（{raw_text}）"
        else:
            label = f"倒计时（{int(delta_sec)} 秒）"

    reminder = await get_reminders_store().add(
        user_id=str(user_id),
        session_id=session_id,
        text=label,
        fire_at=fire_at,
    )
    when_friendly = _format_relative(delta_sec)
    return ActionResult(
        ok=True,
        message=f"好哒，小暖开始计时啦，{when_friendly} 会提醒你的～",
        data={
            "reminder": reminder.to_dict(),
            "fire_in_seconds": int(max(0, delta_sec)),
            "label": label,
        },
    )


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------


async def web_search(params: Dict[str, Any]) -> ActionResult:
    """Search the web for external knowledge.

    Parameters:
        query (str, required): search keywords.
    """
    query = (params.get("query") or params.get("q") or "").strip()
    if not query:
        return ActionResult(
            ok=False,
            message="告诉小暖你想搜什么呀～",
            data={"error": "empty_query"},
        )

    # Check whether search is explicitly disabled (no key configured).
    from shared_runtime.config import get_settings

    settings = get_settings()
    search_api_key = getattr(settings, "search_api_key", None)

    # If no API key is configured at all, return a graceful fallback.
    if not search_api_key:
        return ActionResult(
            ok=False,
            message="抱歉，我现在还连不上搜索引擎，但你可以直接问我，我会尽力回答～",
            data={"error": "search_not_configured", "query": query},
        )

    try:
        provider = get_search_provider()
        result = await provider.search(query)

        if not result.ok:
            return ActionResult(
                ok=False,
                message=f"搜索出了点小问题：{result.error}。直接问我也许也能帮到你～",
                data={"error": result.error, "query": query},
            )

        return ActionResult(
            ok=True,
            message=f"这是小暖帮你搜到的关于「{query}」的信息：\n\n{result.to_text()}",
            data={
                "query": query,
                "source": result.source,
                "results": result.results,
                "answer": result.answer,
            },
        )
    except Exception as exc:
        logger.exception("web_search.error", query=query, error=str(exc))
        return ActionResult(
            ok=False,
            message="搜索时遇到了意外，直接问我吧，小暖会尽力回答你的～",
            data={"error": "unexpected", "detail": str(exc)},
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


BUILTIN_ACTIONS = (
    {
        "name": "get_time",
        "description": "Return the current local time and weekday.",
        "params_schema": {},
        "keywords": ["几点", "现在时间", "今天几号", "what time", "current time"],
        "handler": get_time,
        "needs_api_key": False,
        "category": "util",
        "requires_user_id": False,
    },
    {
        "name": "set_reminder",
        "description": "Create a one-shot or repeating reminder (natural-language delay + optional 每 N 分钟).",
        "params_schema": {
            "user_id": "string",
            "raw_text": "string — original user message; parses '3 分钟后' style delays",
            "text": "string — optional structured body (overrides raw_text body)",
            "delay_seconds": "int — alternative to raw_text for explicit delay",
            "fire_at": "ISO-8601 string — alternative to delay_seconds",
        },
        "keywords": ["提醒我", "提醒一下", "帮我提醒", "remind me", "set reminder", "记得提醒我"],
        "handler": set_reminder,
        "needs_api_key": False,
        "category": "proactive",
        "requires_user_id": True,
    },
    {
        "name": "list_reminders",
        "description": "List pending reminders for the user.",
        "params_schema": {"user_id": "string"},
        "keywords": [
            "我的待办",
            "待办提醒",
            "我有什么提醒",
            "list my reminders",
            "show reminders",
        ],
        "handler": list_reminders,
        "needs_api_key": False,
        "category": "info",
        "requires_user_id": True,
    },
    {
        "name": "cancel_reminder",
        "description": "Cancel a pending reminder by id.",
        "params_schema": {"id": "string", "user_id": "string"},
        "keywords": ["取消提醒", "cancel reminder"],
        "handler": cancel_reminder,
        "needs_api_key": False,
        "category": "proactive",
        "requires_user_id": True,
    },
    {
        "name": "get_weather",
        "description": "Lookup current weather via Open-Meteo (free, no API key).",
        "params_schema": {"location": "string"},
        "keywords": ["天气", "weather"],
        "handler": get_weather,
        "needs_api_key": False,
        "category": "info",
        "requires_user_id": False,
    },
    {
        "name": "query_memory",
        "description": "Query a user's long-term memories and working memory context.",
        "params_schema": {
            "user_id": "string — required",
            "query": "string — optional semantic query",
            "session_id": "string — optional for working memory lookup",
        },
        "keywords": ["记忆", "记得", "query memory", "recall", "remember"],
        "handler": query_memory,
        "needs_api_key": False,
        "category": "info",
        "requires_user_id": True,
    },
    {
        "name": "update_user_profile",
        "description": "Update a user's profile field (preference, name, locale, etc.).",
        "params_schema": {
            "user_id": "string — required",
            "field": "string — e.g. 'name', 'preference', 'locale'",
            "value": "string — new value",
        },
        "keywords": ["更新资料", "设置偏好", "update profile", "改名字"],
        "handler": update_user_profile,
        "needs_api_key": False,
        "category": "util",
        "requires_user_id": True,
    },
    {
        "name": "timer_countdown",
        "description": "Start a countdown timer that fires N seconds/minutes from now.",
        "params_schema": {
            "duration_seconds": "int — explicit seconds",
            "raw_text": "string — e.g. '5 分钟后' parses the delay",
            "user_id": "string — optional, defaults to anonymous",
            "label": "string — optional human-readable label",
        },
        "keywords": ["倒计时", "计时", "timer", "countdown", "计时器"],
        "handler": timer_countdown,
        "needs_api_key": False,
        "category": "proactive",
        "requires_user_id": False,
    },
    {
        "name": "web_search",
        "description": "Search the web for external knowledge (key required; graceful fallback without).",
        "params_schema": {"query": "string — search keywords"},
        "keywords": ["搜索", "查一下", "网上搜", "search", "google", "lookup"],
        "handler": web_search,
        "needs_api_key": True,
        "api_key_env_var": "COMPANION_SEARCH_API_KEY",
        "category": "info",
        "requires_user_id": False,
    },
)


def ensure_builtins_registered() -> None:
    """Idempotent registration of BUILTIN_ACTIONS."""
    registry = get_registry()
    for spec in BUILTIN_ACTIONS:
        if registry.has(spec["name"]):
            continue
        registry.register(
            name=spec["name"],
            description=spec["description"],
            params_schema=spec["params_schema"],
            keywords=list(spec["keywords"]),
            needs_api_key=spec.get("needs_api_key", False),
            api_key_env_var=spec.get("api_key_env_var"),
            category=spec.get("category", "general"),
            requires_user_id=spec.get("requires_user_id", False),
        )(spec["handler"])
    logger.info("action_executor.builtins_registered", count=len(BUILTIN_ACTIONS))


# Register at import time so any caller that imports the module gets the
# built-ins for free. ``ensure_builtins_registered`` remains idempotent
# so explicit init in tests / startup is also safe.
ensure_builtins_registered()
