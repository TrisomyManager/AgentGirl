"""Memory recall logic combining vector search, graph traversal, and persona metrics."""

from typing import List, Optional

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.models import (
    MemoryCategory,
    MemoryEntry,
    MemoryRecallResult,
    RelationshipMetrics,
    WorkingMemorySnapshot,
)

from memory_system.graph_store import graph_store
from memory_system.vector_store import search_similar
from memory_system.working import get_working_memory

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
    entries = await search_similar(
        session=session,
        user_id=user_id,
        query=query,
        top_k=top_k,
        category=category,
        min_importance=min_importance,
    )

    # 2. Knowledge graph facts
    graph_facts: List[str] = []
    if include_graph and settings.enable_knowledge_graph and getattr(graph_store, "_driver", None) is not None:
        try:
            graph_facts = await graph_store.get_user_facts(user_id, limit=top_k * 2)
        except Exception as exc:
            logger.warning("recall.graph_fetch_failed", user_id=user_id, error=str(exc))

    # 3. Relationship metrics from persona_engine
    relationship_snapshot = await _fetch_relationship_metrics(user_id)

    # 4. Build user profile summary from graph
    user_profile_summary = None
    if graph_facts:
        user_profile_summary = (
            f"User {user_id} has {len(graph_facts)} known facts. "
            f"Key facts: {', '.join(graph_facts[:3])}"
        )

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

    result = MemoryRecallResult(
        entries=entries,
        graph_facts=graph_facts,
        relationship_snapshot=relationship_snapshot,
        user_profile_summary=user_profile_summary,
        working_memory=working_memory_snapshot,
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
