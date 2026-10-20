"""Idle-time daily consolidation, with durable checkpoints and host-injected profile updates."""

import asyncio
import hashlib
import json
import re
from collections import Counter
from contextlib import suppress
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, delete, or_, update

from memory_system.graph_index import backfill_graph
from memory_system.lifecycle import lock_memory_epoch, memory_epoch, run_forgetting
from memory_system.session_store import PersistentSessionMemory
from shared_runtime.config import get_settings
from shared_runtime.database import AsyncSessionLocal, Base
from shared_runtime.user_lifecycle import user_scoped

logger = structlog.get_logger(__name__)


class DailySummaryORM(Base):
    __tablename__ = "daily_memory_summaries"
    user_id = Column(String(128), primary_key=True)
    day = Column(String(10), primary_key=True)
    source_fingerprint = Column(String(64), nullable=False)
    summary = Column(Text, nullable=False)
    profile_changes_json = Column(Text, nullable=False, default="{}")
    mood_counts_json = Column(Text, nullable=False, default="{}")
    turn_count = Column(Integer, nullable=False)
    method = Column(String(24), nullable=False)
    profile_synced = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class ConsolidationLeaseORM(Base):
    __tablename__ = "memory_consolidation_leases"
    job_key = Column(String(256), primary_key=True)
    owner = Column(String(32), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


def profile_changes(turns: list[dict]) -> dict:
    """Only explicit user statements update stable preferences, never model-invented facts."""
    likes, dislikes, name = [], [], None
    pattern = re.compile(
        r"我(?:现在|已经)?(?P<verb>不再喜欢|不喜欢|讨厌|更喜欢|很喜欢|最喜欢|喜欢)(?P<thing>[^，。！？!?\n]{1,30})"
    )
    for turn in turns:
        message = turn.get("user_message", "")
        if match := re.search(r"我叫([\w\u4e00-\u9fff·]{1,20})", message):
            name = match.group(1)
        for match in pattern.finditer(message):
            thing = match.group("thing").strip()
            positive = match.group("verb") not in {"不再喜欢", "不喜欢", "讨厌"}
            target, opposite = (likes, dislikes) if positive else (dislikes, likes)
            if thing in opposite:
                opposite.remove(thing)
            if thing not in target:
                target.append(thing)
    result = {"likes": likes[-30:], "dislikes": dislikes[-30:]}
    if name:
        result["display_name"] = name
    return result


class DreamConsolidator:
    def __init__(self, *, summary_generator=None, timezone_reader=None, profile_observer=None,
                 relationship_observer=None):
        self.history = PersistentSessionMemory()
        self.summary_generator = summary_generator
        self.timezone_reader = timezone_reader
        self.profile_observer = profile_observer
        self.relationship_observer = relationship_observer
        self._locks = {}

    async def timezone_for(self, user_id):
        name = await self.timezone_reader(user_id) if self.timezone_reader else get_settings().memory_timezone
        return ZoneInfo(name)

    async def _summarize(self, turns, lease=None):
        excerpt = "\n".join(
            f"用户：{t.get('user_message', '')[:500]}\n助手：{t.get('assistant_message', '')[:200]}" for t in turns
        )
        extractive = "\n".join(
            f"用户：{t.get('user_message', '')[:180]}" for t in turns if t.get("user_message", "").strip()
        )
        if self.summary_generator:
            try:
                candidate = await asyncio.wait_for(self.summary_generator(turns), timeout=30)
                if candidate and str(candidate).strip():
                    return str(candidate).strip()[:4000], "injected"
            except Exception as exc:
                logger.warning("dream.injected_summary_failed", error=type(exc).__name__)
                return extractive[:4000] or "当天没有可整理的用户陈述。", "extractive"
        if get_settings().memory_dream_use_llm:
            from shared_runtime.llm_client import LLMClient

            client = LLMClient()
            if client.has_configured_provider():
                summary = ""
                try:
                    # Merge sequential chunks so the middle of a long day is not silently dropped.
                    for start in range(0, len(excerpt), 7000):
                        if lease and not await self._renew(*lease):
                            raise RuntimeError("consolidation lease expired")
                        result = await asyncio.wait_for(
                            client.generate(
                                system_prompt="整理当日对话回顾。保留用户事实、偏好变化、重要事件、未解决事项和情绪变化；区分用户陈述与助手猜测，不新增事实。只输出中文摘要。",
                                user_message=f"已有回顾：{summary}\n新增摘录：\n{excerpt[start : start + 7000]}",
                                temperature=0.2,
                                max_tokens=1000,
                            ),
                            timeout=12,
                        )
                        candidate = str(result.get("assistant_message") or "").strip()
                        if not candidate:
                            raise ValueError("empty summary")
                        summary = candidate[:4000]
                    return summary, "model"
                except Exception as exc:
                    logger.warning("dream.extractive_fallback", error=type(exc).__name__)
                finally:
                    await client.close()
        # A bounded excerpt is explicitly labelled as an excerpt, never as a model-generated conclusion.
        return extractive[:4000] or "当天没有可整理的用户陈述。", "extractive"

    async def _sync_profile(self, row):
        if row.profile_synced or self.profile_observer is None:
            return
        changes = json.loads(row.profile_changes_json)
        try:
            await self.profile_observer(row.user_id, changes)
        except Exception as exc:
            logger.warning("dream.profile_sync_pending", user_id=row.user_id, error=type(exc).__name__)
            return
        async with AsyncSessionLocal() as session:
            current = await session.get(DailySummaryORM, (row.user_id, row.day))
            if current and current.source_fingerprint == row.source_fingerprint:
                current.profile_synced = True
                await session.commit()
                row.profile_synced = True

    async def _review_relationship(self, user_id, day, turns, fingerprint):
        if self.relationship_observer is None:
            return None
        try:
            return await self.relationship_observer(user_id, day, turns, fingerprint)
        except Exception as exc:
            logger.warning("dream.relationship_review_pending", user_id=user_id, reason=type(exc).__name__)
            return {"status": "pending"}

    @user_scoped()
    async def consolidate(self, user_id: str, day: date | None = None) -> dict:
        async with self._locks.setdefault(user_id, asyncio.Lock()):
            zone = await self.timezone_for(user_id)
            day = day or datetime.now(zone).date()
            key, owner = f"{user_id}:{day.isoformat()}", uuid4().hex
            if not await self._claim(key, owner):
                return {"status": "busy", "user_id": user_id, "day": day.isoformat()}
            try:
                return await self._consolidate_day(user_id, day, zone, (key, owner))
            finally:
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        delete(ConsolidationLeaseORM).where(
                            ConsolidationLeaseORM.job_key == key,
                            ConsolidationLeaseORM.owner == owner,
                        )
                    )
                    await session.commit()

    async def _claim(self, key, owner):
        async with AsyncSessionLocal() as session:
            if session.bind.dialect.name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                from sqlalchemy.dialects.postgresql import insert
            now = datetime.now(UTC)
            await session.execute(
                insert(ConsolidationLeaseORM)
                .values(
                    job_key=key,
                    owner=owner,
                    expires_at=now + timedelta(seconds=120),
                )
                .on_conflict_do_nothing(index_elements=["job_key"])
            )
            result = await session.execute(
                update(ConsolidationLeaseORM)
                .where(
                    ConsolidationLeaseORM.job_key == key,
                    or_(ConsolidationLeaseORM.owner == owner, ConsolidationLeaseORM.expires_at <= now),
                )
                .values(owner=owner, expires_at=now + timedelta(seconds=120))
            )
            await session.commit()
            return bool(result.rowcount)

    async def _renew(self, key, owner):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(ConsolidationLeaseORM)
                .where(
                    ConsolidationLeaseORM.job_key == key,
                    ConsolidationLeaseORM.owner == owner,
                )
                .values(expires_at=datetime.now(UTC) + timedelta(seconds=120))
            )
            await session.commit()
            return bool(result.rowcount)

    async def _consolidate_day(self, user_id, day, zone, lease):
        async with AsyncSessionLocal() as session:
            source_epoch = await memory_epoch(session, user_id)
            await session.commit()
        start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
        turns = await self.history.user_turns(user_id, start=start, end=end)
        turns = [turn for turn in turns if str(turn.get("user_message") or "").strip()]
        if not turns:
            return {"status": "empty", "user_id": user_id, "day": day.isoformat(), "turn_count": 0}
        fingerprint = hashlib.sha256(json.dumps(turns, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        async with AsyncSessionLocal() as session:
            row = await session.get(DailySummaryORM, (user_id, day.isoformat()))
            if row and row.source_fingerprint == fingerprint:
                await self._sync_profile(row)
                review = await self._review_relationship(user_id, day.isoformat(), turns, fingerprint)
                return self.as_dict(row) | {"status": "unchanged", "relationship_review": review}

        summary, method = await self._summarize(turns, lease=lease)
        current_turns = await self.history.user_turns(user_id, start=start, end=end)
        current_turns = [turn for turn in current_turns if str(turn.get("user_message") or "").strip()]
        current_fingerprint = hashlib.sha256(
            json.dumps(current_turns, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        if current_fingerprint != fingerprint or not await self._renew(*lease):
            return {"status": "stale", "user_id": user_id, "day": day.isoformat()}
        changes = profile_changes(turns)
        changes["observed_at"] = turns[-1]["timestamp"]
        moods = Counter((turn.get("metadata") or {}).get("emotion") or "neutral" for turn in turns)
        async with AsyncSessionLocal() as session:
            if not await lock_memory_epoch(session, user_id, expected=source_epoch):
                return {"status": "stale", "user_id": user_id, "day": day.isoformat()}
            row = await session.get(DailySummaryORM, (user_id, day.isoformat()))
            if row is None:
                row = DailySummaryORM(user_id=user_id, day=day.isoformat())
                session.add(row)
            row.source_fingerprint = fingerprint
            row.summary = summary
            row.profile_changes_json = json.dumps(changes, ensure_ascii=False)
            row.mood_counts_json = json.dumps(moods, ensure_ascii=False)
            row.turn_count = len(turns)
            row.method = method
            row.profile_synced = False
            row.updated_at = datetime.now(UTC)
            await session.commit()
        await self._sync_profile(row)
        review = await self._review_relationship(user_id, day.isoformat(), turns, fingerprint)
        return self.as_dict(row) | {"status": "updated", "relationship_review": review}

    @staticmethod
    def as_dict(row):
        updated_at = (
            row.updated_at.replace(tzinfo=UTC) if row.updated_at.tzinfo is None else row.updated_at.astimezone(UTC)
        )
        return {
            "user_id": row.user_id,
            "day": row.day,
            "summary": row.summary,
            "turn_count": row.turn_count,
            "method": row.method,
            "profile_changes": json.loads(row.profile_changes_json),
            "profile_sync_pending": not row.profile_synced,
            "mood_counts": json.loads(row.mood_counts_json),
            "updated_at": updated_at.isoformat(),
        }


class MemoryMaintenanceScheduler:
    def __init__(self, consolidator=None):
        self.consolidator = consolidator or DreamConsolidator()
        self._task = None
        self._stopping = asyncio.Event()

    async def start(self):
        if self._task is None or self._task.done():
            self._stopping = asyncio.Event()
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stopping.set()
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def tick(self, now=None):
        now = now or datetime.now(UTC)
        async with AsyncSessionLocal() as session:
            forgetting = await run_forgetting(session, now=now)
            indexed = await backfill_graph(session)
        semaphore = asyncio.Semaphore(2)

        async def evaluate(user_id):
            async with semaphore:
                completed = 0
                try:
                    zone = await self.consolidator.timezone_for(user_id)
                    local = now.astimezone(zone)
                    if not (2 <= local.hour < 6):
                        return 0
                    recent = await self.consolidator.history.user_turns(user_id, start=now - timedelta(minutes=30))
                    if any(str(turn.get("user_message") or "").strip() for turn in recent):
                        return 0
                    backfill = getattr(get_settings(), "memory_dream_backfill_days", 7)
                    start = datetime.combine(local.date() - timedelta(days=backfill), time.min, tzinfo=zone).astimezone(
                        UTC
                    )
                    end = datetime.combine(local.date(), time.min, tzinfo=zone).astimezone(UTC)
                    pending = await self.consolidator.history.user_turns(user_id, start=start, end=end)
                    days = sorted(
                        {
                            datetime.fromisoformat(turn["timestamp"]).astimezone(zone).date()
                            for turn in pending
                            if str(turn.get("user_message") or "").strip()
                        }
                    )
                    for day in days:
                        result = await self.consolidator.consolidate(user_id, day)
                        completed += result["status"] == "updated"
                except Exception as exc:
                    logger.warning("memory_maintenance.user_failed", user_id=user_id, error=type(exc).__name__)
                return completed

        completed = await asyncio.gather(*(evaluate(user) for user in await self.consolidator.history.users()))
        return forgetting | {"days_consolidated": sum(completed), "memories_indexed": indexed}

    async def _run(self):
        while not self._stopping.is_set():
            try:
                await self.tick()
            except Exception as exc:
                logger.warning("memory_maintenance.tick_failed", error=type(exc).__name__)
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=get_settings().memory_maintenance_interval_seconds
                )


dream_consolidator = DreamConsolidator()
memory_maintenance = MemoryMaintenanceScheduler(dream_consolidator)
