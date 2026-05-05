"""Built-in action handlers.

These are the first three "things 小暖 can actually do":

  - ``get_time``      — replies with the current local time.
  - ``get_weather``   — stub that surfaces a structured "weather not
                        configured" message; intentional placeholder so
                        the integration path is wired even before a
                        weather API key lands.
  - ``set_reminder``  — parses a natural-language delay ("3 分钟后")
                        plus a body ("提醒我喝水"), persists it, and
                        returns the reminder id.
  - ``list_reminders`` — returns the current pending reminders so the
                        chat can answer "我有什么待办的？".
  - ``cancel_reminder`` — flips the cancelled_at flag.

Every handler is async and registered into the process-wide
``ActionRegistry`` at import time via ``ensure_builtins_registered``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog

from action_executor.registry import ActionResult, get_registry
from action_executor.reminders import (
    extract_reminder_body,
    get_reminders_store,
    parse_relative_delay,
)

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
# get_weather (stub — preserves the integration shape)
# ---------------------------------------------------------------------------


async def get_weather(params: Dict[str, Any]) -> ActionResult:
    """Stub: returns a structured 'not configured' message.

    Intent here is to keep the call shape stable so when a weather API
    key lands it's a one-file swap, and so the assistant has a coherent
    fallback today instead of pretending to know.
    """
    location = (params or {}).get("location") or "你所在的地方"
    return ActionResult(
        ok=True,
        message=(
            f"我还没接入实时天气接口呢。等配置好天气 API 后我就能告诉你 {location} 的天气啦。"
            "（你也可以直接告诉我外面是什么天，我帮你记着。）"
        ),
        data={
            "configured": False,
            "location": location,
            "note": "Set COMPANION_WEATHER_API_KEY to enable this handler.",
        },
    )


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

    reminder = await get_reminders_store().add(
        user_id=user_id,
        session_id=session_id,
        text=body,
        fire_at=fire_at,
    )
    delta_sec = (reminder.fire_at - datetime.now(timezone.utc)).total_seconds()
    when_friendly = _format_relative(delta_sec)
    return ActionResult(
        ok=True,
        message=f"好的，我会在 {when_friendly} 提醒你「{body}」。",
        data={"reminder": reminder.to_dict(), "fire_in_seconds": int(max(0, delta_sec))},
    )


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
# Registration
# ---------------------------------------------------------------------------


BUILTIN_ACTIONS = (
    {
        "name": "get_time",
        "description": "Return the current local time and weekday.",
        "params_schema": {},
        "keywords": ["几点", "现在时间", "今天几号", "what time", "current time"],
        "handler": get_time,
    },
    {
        "name": "set_reminder",
        "description": "Create a one-shot reminder that fires at a future time.",
        "params_schema": {
            "user_id": "string",
            "raw_text": "string — original user message; parses '3 分钟后' style delays",
            "text": "string — optional structured body (overrides raw_text body)",
            "delay_seconds": "int — alternative to raw_text for explicit delay",
            "fire_at": "ISO-8601 string — alternative to delay_seconds",
        },
        "keywords": ["提醒我", "提醒一下", "帮我提醒", "remind me", "set reminder", "记得提醒我"],
        "handler": set_reminder,
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
    },
    {
        "name": "cancel_reminder",
        "description": "Cancel a pending reminder by id.",
        "params_schema": {"id": "string", "user_id": "string"},
        "keywords": ["取消提醒", "cancel reminder"],
        "handler": cancel_reminder,
    },
    {
        "name": "get_weather",
        "description": "Lookup current weather (stub until WEATHER_API_KEY configured).",
        "params_schema": {"location": "string"},
        "keywords": ["天气", "weather"],
        "handler": get_weather,
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
        )(spec["handler"])
    logger.info("action_executor.builtins_registered", count=len(BUILTIN_ACTIONS))


# Register at import time so any caller that imports the module gets the
# built-ins for free. ``ensure_builtins_registered`` remains idempotent
# so explicit init in tests / startup is also safe.
ensure_builtins_registered()
