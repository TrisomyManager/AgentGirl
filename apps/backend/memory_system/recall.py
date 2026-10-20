"""Memory recall logic combining vector search, graph traversal, and persona metrics."""

from typing import List, Optional

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from memory_system.dream import DailySummaryORM
from memory_system.graph_index import graph_candidates
from memory_system.graph_lifecycle import cleanup_pending, eligible_memory_ids
from memory_system.graph_store import graph_store
from memory_system.lifecycle import (
    MemoryEpochORM,
    capture_memory_epoch,
    lock_memory_epoch,
    record_recall,
    restore_memory,
)
from memory_system.short_term import short_term_memory
from memory_system.vector_store import search_similar
from memory_system.working import get_working_memory
from shared_contracts.models import (
    MemoryCategory,
    MemoryEntry,
    MemoryRecallResult,
    RelationshipMetrics,
    WorkingMemorySnapshot,
)
from shared_runtime.config import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()

PERSONA_ENGINE_URL = "http://localhost:8001"


async def _fetch_relationship_metrics(user_id: str) -> Optional[RelationshipMetrics]:
    """Fetch relationship metrics from persona_engine via HTTP."""
    if settings.lite_mode:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{PERSONA_ENGINE_URL}/persona/get_profile",
                json={"user_id": user_id},
            )
            if resp.status_code == 200:
                data = resp.json()
                metrics = data.get("relationship") or data.get("relationship_metrics")
                if metrics:
                    return RelationshipMetrics(**metrics)
    except Exception as exc:
        logger.warning("recall.relationship_fetch_failed", user_id=user_id, error=str(exc))
    return None


async def recall_memory(
    session: AsyncSession,
    user_id: str,
    query: str,
    session_id: Optional[str] = None,
    top_k: int = 5,
    include_graph: bool = True,
    category: Optional[MemoryCategory] = None,
    min_importance: Optional[float] = None,
    include_dormant: bool = False,
) -> MemoryRecallResult:
    """Combined memory recall: vector search + graph traversal + relationship metrics."""
    logger.info(
        "recall.start",
        user_id=user_id,
        query=query[:50],
        top_k=top_k,
        include_graph=include_graph,
    )

    # 1. Vector similarity search
    read_epoch = await capture_memory_epoch(user_id)
    semantic_entries = await search_similar(
        session=session,
        user_id=user_id,
        query=query,
        top_k=min(150, top_k * 3),
        category=category,
        min_importance=min_importance,
        include_dormant=include_dormant,
    )

    graph_entries, local_graph_facts = (
        await graph_candidates(
            session,
            user_id,
            query,
            semantic_entries,
            top_k=min(150, top_k * 3),
            category=category,
            min_importance=min_importance,
            include_dormant=include_dormant,
            facts_with_sources=True,
        )
        if include_graph and settings.enable_local_memory_graph
        else ([], [])
    )
    entries = fuse_candidates(semantic_entries, graph_entries, top_k, include_dormant=include_dormant)
    stale_read = not await lock_memory_epoch(session, user_id, expected=read_epoch)
    if not stale_read:
        for entry in entries:
            if include_dormant and entry.expires_at is not None:
                await restore_memory(session, user_id, entry.entry_id, commit=False, record_access=False)
                entry.expires_at = None
        await record_recall(session, user_id, entries)
    else:
        await session.rollback()
        entries = []
    await session.commit()
    previous = await short_term_memory.history.latest_user_digest(user_id, exclude_session_id=session_id)
    daily = (
        await session.execute(
            select(DailySummaryORM)
            .where(
                DailySummaryORM.user_id == user_id,
            )
            .order_by(DailySummaryORM.day.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    # 2. Knowledge graph facts
    external_evidence = []
    if (include_graph and settings.enable_knowledge_graph and getattr(graph_store, "_driver", None) is not None
            and not await cleanup_pending(user_id, session=session)):
        try:
            ids = await eligible_memory_ids(session, user_id, [entry.entry_id for entry in entries])
            external_evidence = await graph_store.get_memory_facts(user_id, memory_ids=list(ids), limit=top_k * 2)
        except Exception as exc:
            logger.warning("recall.graph_fetch_failed", user_id=user_id, error=str(exc))

    # 3. Relationship metrics from persona_engine
    relationship_snapshot = await _fetch_relationship_metrics(user_id)

    # 5. Working memory: rolling per-session context + structured live summary.
    #    Sits orthogonal to the persistent vector / graph layers above. Only
    #    populated when a session_id is known — recall calls without a session
    #    (e.g. cron / batch jobs) will still get persistent-only results.
    working_memory_snapshot: Optional[WorkingMemorySnapshot] = None
    if session_id:
        try:
            wm_state = await get_working_memory().snapshot(session_id)
            if wm_state.turns:
                working_memory_snapshot = WorkingMemorySnapshot(
                    session_id=wm_state.session_id,
                    turn_count=len(wm_state.turns),
                    user_name=wm_state.user_name,
                    user_role=wm_state.user_role,
                    likes=list(wm_state.likes),
                    dislikes=list(wm_state.dislikes),
                    dominant_topic=wm_state.dominant_topic,
                    dominant_topic_heuristic=wm_state.dominant_topic_heuristic,
                    session_digest=wm_state.session_digest,
                    history_digest=wm_state.history_digest,
                    last_user_emotion=wm_state.last_user_emotion,
                    last_assistant_preview=wm_state.last_assistant_preview,
                    recent_turns=[
                        {
                            "turn_id": t.turn_id,
                            "user_message": t.user_message,
                            "assistant_message": t.assistant_message,
                            "emotion": t.emotion,
                            "intent": t.intent,
                            "timestamp": t.timestamp,
                        }
                        for t in wm_state.turns
                    ],
                )
        except Exception as exc:
            logger.warning(
                "recall.working_memory_failed",
                user_id=user_id,
                session_id=session_id,
                error=str(exc),
            )

    # Every fact keeps its SQL source until publication. A delayed graph or
    # profile response cannot restore a deleted/faded source or a cleared digest.
    current_epoch = await session.scalar(select(MemoryEpochORM.epoch).where(MemoryEpochORM.user_id == user_id)) or 0
    if stale_read or current_epoch != read_epoch:
        entries, local_graph_facts, external_evidence = [], [], []
        previous, daily, working_memory_snapshot = {}, None, None
    source_ids = {entry.entry_id for entry in entries} | {
        item["memory_id"] for item in local_graph_facts + external_evidence
    }
    current = await eligible_memory_ids(session, user_id, source_ids)
    entries = [entry for entry in entries if entry.entry_id in current]
    if await cleanup_pending(user_id, session=session):
        external_evidence = []
    graph_facts = list(dict.fromkeys(item["text"] for item in local_graph_facts + external_evidence
                                     if item["memory_id"] in current))
    user_profile_summary = (
        f"User {user_id} has {len(graph_facts)} known facts. Key facts: {', '.join(graph_facts[:3])}"
        if graph_facts else None
    )
    result = MemoryRecallResult(
        entries=entries,
        graph_facts=graph_facts,
        relationship_snapshot=relationship_snapshot,
        user_profile_summary=user_profile_summary,
        working_memory=working_memory_snapshot,
        previous_session_digest=previous.get("digest"),
        daily_summary=daily.summary if daily else None,
        daily_summary_date=daily.day if daily else None,
    )
    logger.info(
        "recall.done",
        user_id=user_id,
        vector_results=len(entries),
        graph_facts=len(graph_facts),
        has_relationship=relationship_snapshot is not None,
        working_memory_turns=working_memory_snapshot.turn_count if working_memory_snapshot else 0,
    )
    return result


def fuse_candidates(
    semantic: List[MemoryEntry], graph: List[MemoryEntry], top_k: int, *, include_dormant: bool = False
) -> List[MemoryEntry]:
    """Weighted reciprocal-rank fusion plus retention, without comparing incompatible score scales."""
    scores = {}
    candidates = {}
    for channel, weight in ((semantic, 1.0), (graph, 0.9)):
        for rank, entry in enumerate(channel):
            if channel is semantic and entry.similarity is not None and entry.similarity < 0.18:
                continue
            if entry.memory_status == "dormant" and not include_dormant:
                # A precise semantic cue can bring a faded memory back; generic graph associations cannot.
                if entry.similarity is None or entry.similarity < 0.8:
                    continue
            salience = entry.effective_importance if entry.effective_importance is not None else entry.importance
            factor = 0.6 + 0.4 * salience
            scores[entry.entry_id] = scores.get(entry.entry_id, 0) + weight * factor / (60 + rank + 1)
            if entry.entry_id not in candidates or entry.similarity is not None:
                candidates[entry.entry_id] = entry
    entries = [candidates[key] for key in sorted(scores, key=scores.get, reverse=True)[:top_k]]
    return entries
