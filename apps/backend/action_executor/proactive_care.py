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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import Column, DateTime, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from action_executor.push_bus import PushEvent, get_proactive_push_bus
from shared_runtime.config import get_settings
from shared_runtime.database import AsyncSessionLocal, Base

logger = structlog.get_logger("action_executor.proactive_care")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_USER_ID = "user_001"

_TRIGGER_META: Dict[str, Dict[str, str]] = {
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
        default=lambda: datetime.now(timezone.utc),
    )


@dataclass
class ProactiveLogEntry:
    """Public dataclass for a logged proactive message."""

    id: str
    user_id: str
    session_id: Optional[str]
    trigger_type: str
    message: str
    created_at: datetime

    @classmethod
    def from_orm(cls, row: ProactiveLogORM) -> "ProactiveLogEntry":
        return cls(
            id=row.id,
            user_id=row.user_id,
            session_id=row.session_id,
            trigger_type=row.trigger_type,
            message=row.message,
            created_at=_ensure_aware(row.created_at),
        )


def _ensure_aware(dt: Optional[datetime]) -> datetime:
    """SQLite returns naive datetimes; coerce to UTC-aware."""
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
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
        session_id: Optional[str] = None,
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
            await session.commit()
            await session.refresh(row)
            return ProactiveLogEntry.from_orm(row)

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[ProactiveLogEntry]:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ProactiveLogORM)
                .where(ProactiveLogORM.user_id == user_id)
                .order_by(ProactiveLogORM.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [ProactiveLogEntry.from_orm(r) for r in rows]

    async def count_today(self, user_id: str) -> int:
        """Count proactive messages sent to a user today (UTC calendar day)."""
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        async with AsyncSessionLocal() as session:
            stmt = select(func.count(ProactiveLogORM.id)).where(
                ProactiveLogORM.user_id == user_id,
                ProactiveLogORM.created_at >= start_of_day,
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def last_sent_for_user(self, user_id: str) -> Optional[datetime]:
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

    async def last_trigger_for_user(
        self, user_id: str, trigger_type: str
    ) -> Optional[datetime]:
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

    async def count_trigger_today(
        self, user_id: str, trigger_type: str
    ) -> int:
        """Count how many times a specific trigger fired for a user today."""
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        async with AsyncSessionLocal() as session:
            stmt = select(func.count(ProactiveLogORM.id)).where(
                ProactiveLogORM.user_id == user_id,
                ProactiveLogORM.trigger_type == trigger_type,
                ProactiveLogORM.created_at >= start_of_day,
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def get_known_user_ids(self) -> List[str]:
        """Return distinct user_ids that have ever received a proactive message."""
        async with AsyncSessionLocal() as session:
            stmt = select(ProactiveLogORM.user_id).distinct()
            rows = (await session.execute(stmt)).scalars().all()
            return list(rows)


_store: Optional[ProactiveLogStore] = None


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
    last_sent_at: Optional[datetime] = None
    next_possible_at: Optional[datetime] = None


class ProactiveCareScheduler:
    """Background task that evaluates trigger conditions and generates proactive messages.

    Follows the exact lifecycle pattern of ``ReminderScheduler``.
    """

    def __init__(self, poll_interval: float = 60.0) -> None:
        self.poll_interval = poll_interval
        self._task: Optional[asyncio.Task[None]] = None
        self._stopping = asyncio.Event()
        self._store = get_proactive_log_store()
        self._bus = get_proactive_push_bus()
        self._settings = get_settings()

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
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, Exception):
                self._task.cancel()
        self._task = None
        logger.info("proactive_care_scheduler.stopped")

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self._tick_once()
            except Exception as exc:
                logger.warning("proactive_care_scheduler.tick_failed", error=str(exc))
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self.poll_interval
                )
            except asyncio.TimeoutError:
                pass

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
        now = datetime.now(timezone.utc)
        local_hour = now.astimezone().hour  # uses system local timezone
        dnd_start = settings.proactive_dnd_start_hour
        dnd_end = settings.proactive_dnd_end_hour
        in_dnd = _in_dnd_window(local_hour, dnd_start, dnd_end)
        if in_dnd:
            return 0

        # --- Discover users ---
        user_ids = await self._resolve_user_ids()
        logger.info(
            "proactive_care.tick",
            user_count=len(user_ids),
            user_ids=user_ids,
            local_hour=local_hour,
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

    async def _evaluate_user(
        self, user_id: str, now: datetime, _in_dnd: bool
    ) -> int:
        """Evaluate all trigger conditions for a single user.

        Evaluation order matters: cooldown + daily cap are gating checks;
        individual triggers run in priority order (idle > greeting > memory).
        """
        settings = self._settings

        # --- Gating: cooldown ---
        last_sent = await self._store.last_sent_for_user(user_id)
        cooldown_seconds = settings.proactive_cooldown_minutes * 60
        if last_sent and (now - last_sent).total_seconds() < cooldown_seconds:
            return 0

        # --- Gating: daily cap ---
        count_today = await self._store.count_today(user_id)
        if count_today >= settings.proactive_max_per_day:
            return 0

        # --- User activity: last_seen ---
        last_seen = await self._get_user_last_seen(user_id)
        hours_inactive = (
            (now - last_seen).total_seconds() / 3600.0 if last_seen else 0.0
        )

        logger.info(
            "proactive_care.eval_user",
            user_id=user_id,
            hours_inactive=round(hours_inactive, 2),
            last_sent=str(last_sent),
            count_today=count_today,
            local_hour=now.astimezone().hour,
        )

        generated = 0

        # 1. Idle check-in (highest priority — don't stack with greetings)
        if hours_inactive * 60 >= settings.proactive_idle_checkin_minutes:
            if await self._try_trigger(user_id, "idle_checkin", now):
                await self._fire_proactive(
                    user_id=user_id,
                    trigger_type="idle_checkin",
                    context={"hours_inactive": round(hours_inactive, 1)},
                    now=now,
                )
                generated += 1
                return generated  # only one trigger per tick per user

        # 2. Time-of-day greetings (only if user was recently active or it's the right hour)
        local_hour = now.astimezone().hour
        if settings.proactive_morning_greeting_enabled and 6 <= local_hour <= 9:
            if await self._try_trigger(user_id, "morning_greeting", now):
                await self._fire_proactive(
                    user_id=user_id,
                    trigger_type="morning_greeting",
                    context={"local_hour": local_hour},
                    now=now,
                )
                generated += 1
                return generated

        if settings.proactive_evening_greeting_enabled and 17 <= local_hour <= 20:
            if await self._try_trigger(user_id, "evening_greeting", now):
                await self._fire_proactive(
                    user_id=user_id,
                    trigger_type="evening_greeting",
                    context={"local_hour": local_hour},
                    now=now,
                )
                generated += 1
                return generated

        # 3. Memory follow-up (only if user has been inactive a while)
        if (
            settings.proactive_memory_followup_enabled
            and hours_inactive >= 120  # 5 days minimum for memory follow-up
        ):
            memory_context = await self._get_memory_followup_context(user_id)
            if memory_context and await self._try_trigger(
                user_id, "memory_followup", now
            ):
                await self._fire_proactive(
                    user_id=user_id,
                    trigger_type="memory_followup",
                    context=memory_context,
                    now=now,
                )
                generated += 1

        return generated

    # ------------------------------------------------------------------
    # Trigger helpers
    # ------------------------------------------------------------------

    async def _try_trigger(
        self, user_id: str, trigger_type: str, now: datetime
    ) -> bool:
        """Check if a specific trigger should fire for a user right now.

        Enforces:
        - The trigger is enabled in settings
        - It hasn't already fired today (for greetings)
        - For idle: user hasn't already received an idle checkin recently
        """
        settings = self._settings

        # Check per-trigger enablement
        if trigger_type == "morning_greeting" and not settings.proactive_morning_greeting_enabled:
            return False
        if trigger_type == "evening_greeting" and not settings.proactive_evening_greeting_enabled:
            return False
        if trigger_type == "memory_followup" and not settings.proactive_memory_followup_enabled:
            return False

        # Greetings: only once per day
        if trigger_type in ("morning_greeting", "evening_greeting"):
            today_count = await self._store.count_trigger_today(
                user_id, trigger_type
            )
            if today_count > 0:
                return False

        return True

    async def _fire_proactive(
        self,
        user_id: str,
        trigger_type: str,
        context: Dict[str, Any],
        now: datetime,
    ) -> None:
        """Generate a proactive message, log it, and push to the frontend."""
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
            return

        message = result.get("assistant_message", "")
        if not message.strip():
            return

        emotion = result.get("emotion", {})

        # Persist
        entry = await self._store.add(
            user_id=user_id,
            trigger_type=trigger_type,
            message=message,
            session_id=result.get("session_id"),
        )

        # Push
        event_id = str(uuid.uuid4())
        await self._bus.publish(
            PushEvent(
                kind="proactive_message",
                payload={
                    "id": entry.id,
                    "user_id": user_id,
                    "message": message,
                    "trigger_type": trigger_type,
                    "timestamp": now.isoformat(),
                    "emotion": emotion.get("primary") if emotion else None,
                },
            )
        )

        logger.info(
            "proactive_care_scheduler.message_fired",
            id=entry.id,
            user_id=user_id,
            trigger_type=trigger_type,
            message_preview=message[:80],
        )

    # ------------------------------------------------------------------
    # Orchestrator bridge
    # ------------------------------------------------------------------

    async def _call_orchestrator(
        self,
        user_id: str,
        trigger_type: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Route to the orchestrator's proactive generation path.

        This is the bridge between the scheduler and the LLM pipeline.
        Uses in-process call in monolithic mode.
        """
        from core_orchestrator.orchestrator import get_orchestrator

        orch = await get_orchestrator()
        session_id = await self._resolve_session_id(user_id)
        return await orch.generate_proactive_turn(
            user_id=user_id,
            session_id=session_id,
            trigger_type=trigger_type,
            trigger_context=context,
        )

    async def _resolve_session_id(self, user_id: str) -> str:
        """Find the most recent session for a user, or create a proactive one."""
        try:
            from memory_system.working import get_working_memory

            wm = get_working_memory()
            # Use a dedicated proactive session per user
            return f"proactive_{user_id}"
        except Exception:
            return f"proactive_{user_id}"

    async def _resolve_user_ids(self) -> List[str]:
        """Discover user IDs to evaluate.

        Prioritises the default user, then any user who has received a
        proactive message before, then any user with recorded interactions.
        """
        ids: List[str] = []
        # Always include the default user
        ids.append(DEFAULT_USER_ID)

        # Add users from proactive_log
        try:
            known = await self._store.get_known_user_ids()
            for uid in known:
                if uid not in ids:
                    ids.append(uid)
        except Exception:
            pass

        # Try to discover users from the relationship tracker
        try:
            from persona_engine.runtime import get_relationship_tracker

            tracker = get_relationship_tracker()
            metrics = await tracker.get_metrics(DEFAULT_USER_ID)
            if metrics and metrics.total_interactions > 0:
                if DEFAULT_USER_ID not in ids:
                    ids.append(DEFAULT_USER_ID)
        except Exception:
            pass

        return ids

    async def _get_user_last_seen(self, user_id: str) -> Optional[datetime]:
        """Get the last time a user interacted with the companion."""
        try:
            from persona_engine.runtime import get_relationship_tracker

            tracker = get_relationship_tracker()
            metrics = await tracker.get_metrics(user_id)
            if metrics and metrics.last_seen:
                return _ensure_aware(metrics.last_seen)
        except Exception:
            pass
        return None

    async def _get_memory_followup_context(
        self, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Find a high-importance memory entry suitable for follow-up."""
        try:
            from memory_system.recall import recall_memory

            result = await recall_memory(
                query="recent important memories",
                user_id=user_id,
                session_id=None,
                top_k=5,
                include_graph=False,
            )
            for entry in result.entries:
                if getattr(entry, "importance", 0) >= 0.7:
                    return {
                        "memory_content": getattr(entry, "content", str(entry)),
                        "memory_category": getattr(entry, "category", ""),
                    }
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

    def user_proactive_rules(self, user_id: str) -> List[Dict[str, Any]]:
        """Return the proactive rules list consumed by the frontend.

        Called by ``user_state.py`` for ``GET /actions/user_state``.
        """
        settings = self._settings
        if not settings.proactive_enabled:
            return []

        rules: List[Dict[str, Any]] = []
        for trigger_type, meta in _TRIGGER_META.items():
            enabled = True
            if trigger_type == "morning_greeting":
                enabled = settings.proactive_morning_greeting_enabled
            elif trigger_type == "evening_greeting":
                enabled = settings.proactive_evening_greeting_enabled
            elif trigger_type == "memory_followup":
                enabled = settings.proactive_memory_followup_enabled

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

_scheduler: Optional[ProactiveCareScheduler] = None


def get_proactive_care_scheduler(**kwargs: Any) -> ProactiveCareScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = ProactiveCareScheduler(**kwargs)
    return _scheduler
