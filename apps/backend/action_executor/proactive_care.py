"""Proactive care scheduler — V2.5 主动关怀引擎.

Background polling loop that evaluates trigger conditions (idle check-in,
time-of-day greeting, memory follow-up) and generates AI-initiated messages
via the orchestrator. Delivered to the frontend through the existing
``ProactivePushBus`` → SSE ``/actions/push`` pipeline.

Schema: ``proactive_log`` table on the shared ``Base.metadata``::

    id            string PK (uuid4 hex)
    user_id       string indexed
    session_id    string nullable
    trigger_type  string — idle_checkin | morning_greeting | evening_greeting | memory_followup
    message       text — the generated proactive message
    created_at    datetime UTC

Mirrors the ``ReminderScheduler`` lifecycle pattern exactly:
``asyncio.Event`` stop signal, ``asyncio.wait_for`` tick timing,
exception-guarded tick function.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import Column, DateTime, String, Text, func, select

from action_executor.proactive_preferences import care_preferences_store
from action_executor.push_bus import PushEvent, get_proactive_push_bus
from shared_runtime.config import get_settings
from shared_runtime.database import AsyncSessionLocal, Base
from shared_runtime.user_lifecycle import user_scoped

logger = structlog.get_logger("action_executor.proactive_care")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_USER_ID = "user_001"

_TRIGGER_META: dict[str, dict[str, str]] = {
    "idle_checkin": {
        "label": "长时间未互动问候",
        "schedule": "长时间未互动时自动",
        "description": "你长时间不说话时主动关心你",
    },
    "morning_greeting": {
        "label": "早晨问候",
        "schedule": "每天早晨",
        "description": "每天早上用温暖愉快的语气道早安",
    },
    "evening_greeting": {
        "label": "晚间关怀",
        "schedule": "每天傍晚",
        "description": "傍晚时关心你一天过得怎么样",
    },
    "memory_followup": {
        "label": "记忆关怀",
        "schedule": "根据最近话题",
        "description": "记得你在意的事并主动 follow-up",
    },
}


# ---------------------------------------------------------------------------
# ORM
# ---------------------------------------------------------------------------


class ProactiveLogORM(Base):
    """Persistent log of every proactive message generated."""

    __tablename__ = "proactive_log"

    id = Column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True)
    trigger_type = Column(String(32), nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


@dataclass
class ProactiveLogEntry:
    """Public dataclass for a logged proactive message."""

    id: str
    user_id: str
    session_id: str | None
    trigger_type: str
    message: str
    created_at: datetime

    @classmethod
    def from_orm(cls, row: ProactiveLogORM) -> ProactiveLogEntry:
        return cls(
            id=row.id,
            user_id=row.user_id,
            session_id=row.session_id,
            trigger_type=row.trigger_type,
            message=row.message,
            created_at=_ensure_aware(row.created_at),
        )


def _ensure_aware(dt: datetime | None) -> datetime:
    """SQLite returns naive datetimes; coerce to UTC-aware."""
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class ProactiveLogStore:
    """Async CRUD on the proactive_log table."""

    async def add(
        self,
        user_id: str,
        trigger_type: str,
        message: str,
        session_id: str | None = None,
        push_event: PushEvent | None = None,
        event_store=None,
    ) -> ProactiveLogEntry:
        row = ProactiveLogORM(
            id=uuid.uuid4().hex,
            user_id=user_id,
            session_id=session_id,
            trigger_type=trigger_type,
            message=message,
        )
        async with AsyncSessionLocal() as session:
            session.add(row)
            if push_event is not None and event_store is not None:
                push_event.payload["id"] = row.id
                await event_store.enqueue(session, push_event)
            await session.commit()
            await session.refresh(row)
            return ProactiveLogEntry.from_orm(row)

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 20,
    ) -> list[ProactiveLogEntry]:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ProactiveLogORM)
                .where(ProactiveLogORM.user_id == user_id)
                .order_by(ProactiveLogORM.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [ProactiveLogEntry.from_orm(r) for r in rows]

    async def count_today(self, user_id: str, timezone_name: str = "UTC") -> int:
        """Count proactive messages sent to a user today (UTC calendar day)."""
        now = datetime.now(ZoneInfo(timezone_name))
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        async with AsyncSessionLocal() as session:
            stmt = select(func.count(ProactiveLogORM.id)).where(
                ProactiveLogORM.user_id == user_id,
                ProactiveLogORM.created_at >= start_of_day,
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def last_sent_for_user(self, user_id: str) -> datetime | None:
        """Return ``created_at`` of the most recent proactive message for a user."""
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ProactiveLogORM.created_at)
                .where(ProactiveLogORM.user_id == user_id)
                .order_by(ProactiveLogORM.created_at.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _ensure_aware(row) if row else None

    async def last_trigger_for_user(self, user_id: str, trigger_type: str) -> datetime | None:
        """Return when a specific trigger type was last fired for a user."""
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ProactiveLogORM.created_at)
                .where(
                    ProactiveLogORM.user_id == user_id,
                    ProactiveLogORM.trigger_type == trigger_type,
                )
                .order_by(ProactiveLogORM.created_at.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _ensure_aware(row) if row else None

    async def count_trigger_today(self, user_id: str, trigger_type: str, timezone_name: str = "UTC") -> int:
        """Count how many times a specific trigger fired for a user today."""
        now = datetime.now(ZoneInfo(timezone_name))
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        async with AsyncSessionLocal() as session:
            stmt = select(func.count(ProactiveLogORM.id)).where(
                ProactiveLogORM.user_id == user_id,
                ProactiveLogORM.trigger_type == trigger_type,
                ProactiveLogORM.created_at >= start_of_day,
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def get_known_user_ids(self) -> list[str]:
        """Return distinct user_ids that have ever received a proactive message."""
        async with AsyncSessionLocal() as session:
            stmt = select(ProactiveLogORM.user_id).distinct()
            rows = (await session.execute(stmt)).scalars().all()
            return list(rows)


_store: ProactiveLogStore | None = None


def get_proactive_log_store() -> ProactiveLogStore:
    global _store
    if _store is None:
        _store = ProactiveLogStore()
    return _store


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


@dataclass
class _RuleState:
    """Internal snapshot of what the scheduler knows about a user + trigger."""

    enabled: bool = True
    last_sent_at: datetime | None = None
    next_possible_at: datetime | None = None


class ProactiveCareScheduler:
    """Background task that evaluates trigger conditions and generates proactive messages.

    Follows the exact lifecycle pattern of ``ReminderScheduler``.
    """

    def __init__(self, poll_interval: float = 60.0) -> None:
        self.poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._store = get_proactive_log_store()
        self._bus = get_proactive_push_bus()
        self._settings = get_settings()
        self._user_tasks: dict[str, asyncio.Task[None]] = {}
        self._generate_turn = None
        self._memory_context_reader = None
        self._delivery_observer = None

    def configure(self, *, generate_turn=None, memory_context_reader=None, delivery_observer=None) -> None:
        """Inject host adapters; this module has no dependency on an orchestrator or memory engine."""
        self._generate_turn = generate_turn
        self._memory_context_reader = memory_context_reader
        self._delivery_observer = delivery_observer

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "proactive_care_scheduler.started",
            poll_interval=self.poll_interval,
        )

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None
        for task in self._user_tasks.values():
            task.cancel()
        if self._user_tasks:
            await asyncio.gather(*self._user_tasks.values(), return_exceptions=True)
        self._user_tasks.clear()
        logger.info("proactive_care_scheduler.stopped")

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                for user_id in await self._resolve_user_ids():
                    task = self._user_tasks.get(user_id)
                    if task is None or task.done():
                        self._user_tasks[user_id] = asyncio.create_task(self._user_loop(user_id))
            except Exception as exc:
                logger.warning("proactive_care_scheduler.tick_failed", error=str(exc))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_interval)

    async def _user_loop(self, user_id: str) -> None:
        """One bounded evaluator per user; one slow model call cannot block other users."""
        while not self._stopping.is_set():
            try:
                await self._evaluate_user(user_id, datetime.now(UTC), False)
            except Exception as exc:
                logger.warning("proactive_care.user_loop_failed", user_id=user_id, error=str(exc))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=max(1.0, self.poll_interval))

    # ------------------------------------------------------------------
    # Tick — the evaluation engine
    # ------------------------------------------------------------------

    async def _tick_once(self) -> int:
        """Evaluate all trigger conditions and fire appropriate messages.

        Returns the number of proactive messages generated this tick.
        """
        settings = self._settings
        if not settings.proactive_enabled:
            return 0

        # --- Do-not-disturb window ---
        now = datetime.now(UTC)
        in_dnd = False  # Per-user timezones and DND are evaluated below.

        # --- Discover users ---
        user_ids = await self._resolve_user_ids()
        logger.info(
            "proactive_care.tick",
            user_count=len(user_ids),
            user_ids=user_ids,
            in_dnd=in_dnd,
        )

        generated = 0

        for user_id in user_ids:
            try:
                generated += await self._evaluate_user(user_id, now, in_dnd)
            except Exception as exc:
                logger.warning(
                    "proactive_care_scheduler.user_eval_failed",
                    user_id=user_id,
                    error=str(exc),
                )
        return generated

    @user_scoped()
    async def _evaluate_user(self, user_id: str, now: datetime, _in_dnd: bool) -> int:
        """Evaluate all trigger conditions for a single user.

        Evaluation order matters: cooldown + daily cap are gating checks;
        individual triggers run in priority order (idle > greeting > memory).
        """
        settings = self._settings
        preferences = await care_preferences_store.get(user_id)
        local_hour = now.astimezone(ZoneInfo(preferences.timezone)).hour
        if (
            not settings.proactive_enabled
            or not preferences.enabled
            or _in_dnd_window(local_hour, preferences.dnd_start_hour, preferences.dnd_end_hour)
        ):
            return 0

        # --- Gating: cooldown ---
        last_sent = await self._store.last_sent_for_user(user_id)
        cooldown_seconds = preferences.cooldown_minutes * 60
        if last_sent and (now - last_sent).total_seconds() < cooldown_seconds:
            return 0

        # --- Gating: daily cap ---
        count_today = await self._store.count_today(user_id, preferences.timezone)
        if count_today >= preferences.max_per_day:
            return 0

        # --- User activity: last_seen ---
        last_seen = await self._get_user_last_seen(user_id)
        hours_inactive = (now - last_seen).total_seconds() / 3600.0 if last_seen else 0.0

        logger.info(
            "proactive_care.eval_user",
            user_id=user_id,
            hours_inactive=round(hours_inactive, 2),
            last_sent=str(last_sent),
            count_today=count_today,
            local_hour=local_hour,
        )

        generated = 0

        # Specific remembered concerns take precedence over a generic idle greeting.
        if preferences.memory_followup and hours_inactive >= 120:
            memory_context = await self._get_memory_followup_context(user_id)
            if memory_context and await self._try_trigger(user_id, "memory_followup", now):
                return int(
                    await self._fire_proactive(
                        user_id=user_id,
                        trigger_type="memory_followup",
                        context=memory_context,
                        now=now,
                    )
                )

        # 1. Idle check-in (don't stack with greetings)
        if (
            preferences.idle_checkin
            and hours_inactive * 60 >= settings.proactive_idle_checkin_minutes
            and await self._try_trigger(user_id, "idle_checkin", now)
        ):
            return int(
                await self._fire_proactive(
                    user_id=user_id,
                    trigger_type="idle_checkin",
                    context={"hours_inactive": round(hours_inactive, 1)},
                    now=now,
                )
            )

        # 2. Time-of-day greetings (only if user was recently active or it's the right hour)
        if (
            preferences.morning_greeting
            and 6 <= local_hour <= 9
            and await self._try_trigger(user_id, "morning_greeting", now)
        ):
            return int(
                await self._fire_proactive(
                    user_id=user_id,
                    trigger_type="morning_greeting",
                    context={"local_hour": local_hour},
                    now=now,
                )
            )

        if (
            preferences.evening_greeting
            and 17 <= local_hour <= 20
            and await self._try_trigger(user_id, "evening_greeting", now)
        ):
            return int(
                await self._fire_proactive(
                    user_id=user_id,
                    trigger_type="evening_greeting",
                    context={"local_hour": local_hour},
                    now=now,
                )
            )

        return generated

    # ------------------------------------------------------------------
    # Trigger helpers
    # ------------------------------------------------------------------

    async def _try_trigger(self, user_id: str, trigger_type: str, now: datetime) -> bool:
        """Check if a specific trigger should fire for a user right now.

        Enforces:
        - The trigger is enabled in settings
        - It hasn't already fired today (for greetings)
        - For idle: user hasn't already received an idle checkin recently
        """
        settings = self._settings
        preferences = await care_preferences_store.get(user_id)
        if not preferences.enabled or not getattr(preferences, trigger_type, False):
            return False

        # Check per-trigger enablement
        if trigger_type == "morning_greeting" and not settings.proactive_morning_greeting_enabled:
            return False
        if trigger_type == "evening_greeting" and not settings.proactive_evening_greeting_enabled:
            return False
        if trigger_type == "memory_followup" and not settings.proactive_memory_followup_enabled:
            return False

        # Greetings: only once per day
        if trigger_type in ("morning_greeting", "evening_greeting"):
            today_count = await self._store.count_trigger_today(user_id, trigger_type, preferences.timezone)
            if today_count > 0:
                return False

        return True

    async def _fire_proactive(
        self,
        user_id: str,
        trigger_type: str,
        context: dict[str, Any],
        now: datetime,
    ) -> bool:
        """Generate a proactive message, log it, and push to the frontend."""
        activity_before, _ = await care_preferences_store.activity(user_id)
        try:
            result = await self._call_orchestrator(
                user_id=user_id,
                trigger_type=trigger_type,
                context=context,
            )
        except Exception as exc:
            logger.warning(
                "proactive_care_scheduler.orchestrator_call_failed",
                user_id=user_id,
                trigger_type=trigger_type,
                error=str(exc),
            )
            return False

        message = result.get("assistant_message", "")
        if not message.strip():
            return False

        emotion = result.get("emotion", {})
        preferences = await care_preferences_store.get(user_id)
        activity_after, _ = await care_preferences_store.activity(user_id)
        current_hour = datetime.now(ZoneInfo(preferences.timezone)).hour
        if (
            not preferences.enabled
            or not getattr(preferences, trigger_type, False)
            or activity_before != activity_after
        ):
            return False
        if _in_dnd_window(current_hour, preferences.dnd_start_hour, preferences.dnd_end_hour):
            return False
        if await self._store.count_today(user_id, preferences.timezone) >= preferences.max_per_day:
            return False
        event = PushEvent(
            kind="proactive_message",
            payload={
                "user_id": user_id,
                "message": message,
                "trigger_type": trigger_type,
                "timestamp": now.isoformat(),
                "emotion": emotion.get("primary") if emotion else None,
            },
        )

        # Persist
        entry = await self._store.add(
            user_id=user_id,
            trigger_type=trigger_type,
            message=message,
            session_id=result.get("session_id"),
            push_event=event,
            event_store=self._bus.event_store,
        )

        # Push
        event.payload["id"] = entry.id
        await self._bus.publish(event)
        if self._delivery_observer is not None:
            try:
                await self._delivery_observer(
                    user_id=user_id, session_id=entry.session_id, message=message, event_id=entry.id
                )
            except Exception as exc:
                logger.warning("proactive_care.delivery_observer_failed", error=type(exc).__name__)

        logger.info(
            "proactive_care_scheduler.message_fired",
            id=entry.id,
            user_id=user_id,
            trigger_type=trigger_type,
            message_preview=message[:80],
        )
        return True

    # ------------------------------------------------------------------
    # Orchestrator bridge
    # ------------------------------------------------------------------

    async def _call_orchestrator(
        self,
        user_id: str,
        trigger_type: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Route to the orchestrator's proactive generation path.

        This is the bridge between the scheduler and the LLM pipeline.
        Uses in-process call in monolithic mode.
        """
        if self._generate_turn is None:
            raise RuntimeError("Host must configure a proactive turn generator")
        session_id = await self._resolve_session_id(user_id)
        return await self._generate_turn(
            user_id=user_id,
            session_id=session_id,
            trigger_type=trigger_type,
            trigger_context=context,
        )

    async def _resolve_session_id(self, user_id: str) -> str:
        """Find the most recent session for a user, or create a proactive one."""
        _, session_id = await care_preferences_store.activity(user_id)
        return session_id or f"proactive_{user_id}"

    async def _resolve_user_ids(self) -> list[str]:
        """Discover user IDs to evaluate.

        Prioritises the default user, then any user who has received a
        proactive message before, then any user with recorded interactions.
        """
        ids = await care_preferences_store.users()

        # Add users from proactive_log
        try:
            known = await self._store.get_known_user_ids()
            for uid in known:
                if uid not in ids:
                    ids.append(uid)
        except Exception:
            pass

        return ids

    async def _get_user_last_seen(self, user_id: str) -> datetime | None:
        """Get the last time a user interacted with the companion."""
        last_seen, _ = await care_preferences_store.activity(user_id)
        if last_seen is not None:
            return last_seen
        return None

    async def _get_memory_followup_context(self, user_id: str) -> dict[str, Any] | None:
        """Find a high-importance memory entry suitable for follow-up."""
        try:
            if self._memory_context_reader is not None:
                return await self._memory_context_reader(user_id)
        except Exception as exc:
            logger.debug(
                "proactive_care.memory_context_failed",
                user_id=user_id,
                error=str(exc),
            )
        return None

    # ------------------------------------------------------------------
    # Public: user_proactive_rules
    # ------------------------------------------------------------------

    async def user_proactive_rules(self, user_id: str) -> list[dict[str, Any]]:
        """Return the proactive rules list consumed by the frontend.

        Called by ``user_state.py`` for ``GET /actions/user_state``.
        """
        settings = self._settings
        preferences = await care_preferences_store.get(user_id)

        rules: list[dict[str, Any]] = []
        for trigger_type, meta in _TRIGGER_META.items():
            enabled = settings.proactive_enabled and preferences.enabled and getattr(preferences, trigger_type)

            rules.append(
                {
                    "id": trigger_type,
                    "title": meta["label"],
                    "enabled": enabled,
                    "schedule": meta["schedule"],
                    "next_run_at": None,  # computed lazily per tick
                }
            )
        return rules


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _in_dnd_window(local_hour: int, dnd_start: int, dnd_end: int) -> bool:
    """Check if ``local_hour`` falls inside the do-not-disturb window.

    Supports overnight windows (e.g. 22–07) where start > end.
    """
    if dnd_start == dnd_end:
        return False
    if dnd_start > dnd_end:
        # overnight: 22:00 → 07:00
        return local_hour >= dnd_start or local_hour < dnd_end
    else:
        # same-day: 13:00 → 14:00
        return dnd_start <= local_hour < dnd_end


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_scheduler: ProactiveCareScheduler | None = None


def get_proactive_care_scheduler(**kwargs: Any) -> ProactiveCareScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = ProactiveCareScheduler(**kwargs)
    return _scheduler
