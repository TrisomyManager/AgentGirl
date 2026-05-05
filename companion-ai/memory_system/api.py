"""FastAPI routers for the memory system."""

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from shared.events import MemoryRecallEvent, MemorySyncEvent
from shared.models import MemoryCategory, MemoryEntry, MemoryRecallResult

from memory_system.db import get_db
from memory_system.graph_store import graph_store
from memory_system.pipeline import run_memory_pipeline
from memory_system.recall import recall_memory
from memory_system.short_term import short_term_memory
from memory_system.vector_store import (
    decay_low_importance,
    delete_expired,
    delete_memory_by_id,
    delete_user_memories,
    get_user_memory_summary,
    list_user_memories,
    store_memory,
)
from memory_system.working import get_working_memory

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class StoreMemoryRequest(BaseModel):
    user_id: str
    category: MemoryCategory = MemoryCategory.FACT
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    emotion_tags: List[str] = Field(default_factory=list)
    source_turn_id: Optional[str] = None
    embedding: Optional[List[float]] = None


class RecallRequest(BaseModel):
    query: str
    user_id: str
    session_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=50)
    include_graph: bool = True
    category: Optional[MemoryCategory] = None
    min_importance: Optional[float] = None


class GraphQueryRequest(BaseModel):
    cypher: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class PipelineTriggerRequest(BaseModel):
    turn_id: str
    user_id: str
    user_message: str
    assistant_message: str
    emotion: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UserSummaryResponse(BaseModel):
    user_id: str
    total_memories: int
    avg_importance: float
    last_memory: Optional[str] = None
    by_category: Dict[str, int]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/store", response_model=MemoryEntry)
async def store_memory_endpoint(
    req: StoreMemoryRequest,
    session: AsyncSession = Depends(get_db),
) -> MemoryEntry:
    """Store a memory entry directly into long-term memory."""
    entry = MemoryEntry(
        entry_id="",
        user_id=req.user_id,
        category=req.category,
        content=req.content,
        importance=req.importance,
        emotion_tags=[tag for tag in req.emotion_tags],
        source_turn_id=req.source_turn_id,
        embedding=req.embedding,
    )
    result = await store_memory(session, entry)
    logger.info("api.memory_stored", entry_id=result.entry_id, user_id=req.user_id)
    return result


@router.post("/recall", response_model=MemoryRecallResult)
async def recall_memory_endpoint(
    req: RecallRequest,
    session: AsyncSession = Depends(get_db),
) -> MemoryRecallResult:
    """Semantic recall combining vector search and knowledge graph."""
    result = await recall_memory(
        session=session,
        user_id=req.user_id,
        query=req.query,
        session_id=req.session_id,
        top_k=req.top_k,
        include_graph=req.include_graph,
        category=req.category,
        min_importance=req.min_importance,
    )
    logger.info(
        "api.memory_recalled",
        user_id=req.user_id,
        results=len(result.entries),
        graph_facts=len(result.graph_facts),
    )
    return result


@router.post("/graph_query")
async def graph_query_endpoint(req: GraphQueryRequest) -> List[Dict[str, Any]]:
    """Run a raw Cypher query on the knowledge graph."""
    try:
        results = await graph_store.query(req.cypher, req.parameters)
        logger.info("api.graph_queried", cypher=req.cypher[:50], results=len(results))
        return results
    except Exception as exc:
        logger.error("api.graph_query_failed", error=str(exc))
        raise HTTPException(status_code=400, detail=f"Graph query failed: {exc}") from exc


@router.post("/pipeline/trigger")
async def trigger_pipeline_endpoint(req: PipelineTriggerRequest) -> Dict[str, Any]:
    """Manually trigger the 5-stage memory pipeline for a conversation turn."""
    turn_data = {
        "turn_id": req.turn_id,
        "user_id": req.user_id,
        "user_message": req.user_message,
        "assistant_message": req.assistant_message,
        "emotion": req.emotion,
        "metadata": req.metadata,
    }
    # Run asynchronously via Celery
    task = run_memory_pipeline.delay(turn_data)
    logger.info(
        "api.pipeline_triggered",
        turn_id=req.turn_id,
        task_id=task.id,
    )
    return {"task_id": task.id, "status": "queued", "turn_id": req.turn_id}


@router.get("/user/{user_id}/list", response_model=List[MemoryEntry])
async def list_memories_endpoint(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    category: Optional[MemoryCategory] = None,
    session: AsyncSession = Depends(get_db),
) -> List[MemoryEntry]:
    """List a user's memories newest-first, with optional category filter."""
    return await list_user_memories(
        session=session,
        user_id=user_id,
        limit=min(limit, 200),
        offset=max(offset, 0),
        category=category,
    )


@router.delete("/user/{user_id}/all")
async def delete_all_user_memories(
    user_id: str,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, int]:
    """Wipe all memories for a user."""
    n = await delete_user_memories(session, user_id)
    logger.info("api.user_memories_deleted", user_id=user_id, count=n)
    return {"deleted": n}


@router.delete("/{memory_id}")
async def delete_memory_endpoint(
    memory_id: str,
    session: AsyncSession = Depends(get_db),
) -> Dict[str, bool]:
    """Delete a single memory by id."""
    ok = await delete_memory_by_id(session, memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"deleted": True}


@router.post("/pipeline/run_sync")
async def run_pipeline_sync_endpoint(
    req: PipelineTriggerRequest,
) -> Dict[str, Any]:
    """Run the 5-stage pipeline in-process (no Celery). Used in lite/monolithic mode."""
    from memory_system.pipeline import run_pipeline_async
    turn_data = {
        "turn_id": req.turn_id,
        "user_id": req.user_id,
        "user_message": req.user_message,
        "assistant_message": req.assistant_message,
        "emotion": req.emotion,
        "metadata": req.metadata,
    }
    result = await run_pipeline_async(turn_data)
    return {
        "memory_entry_id": result.get("memory_entry_id"),
        "category": result.get("memory_category"),
        "importance": result.get("importance"),
        "importance_reason": result.get("importance_reason"),
        "extracted": result.get("extracted"),
    }


@router.get("/user/{user_id}/summary", response_model=UserSummaryResponse)
async def get_user_summary(
    user_id: str,
    session: AsyncSession = Depends(get_db),
) -> UserSummaryResponse:
    """Get a summary of a user's memories."""
    summary = await get_user_memory_summary(session, user_id)
    last = summary.get("last_memory")
    last_str: Optional[str]
    if last is None:
        last_str = None
    elif hasattr(last, "isoformat"):
        last_str = last.isoformat()
    else:
        last_str = str(last)
    return UserSummaryResponse(
        user_id=user_id,
        total_memories=summary.get("total_memories", 0),
        avg_importance=float(summary.get("avg_importance") or 0.0),
        last_memory=last_str,
        by_category=summary.get("by_category", {}),
    )


@router.post("/maintenance/decay")
async def run_decay_maintenance(session: AsyncSession = Depends(get_db)) -> Dict[str, int]:
    """Run memory decay and expiration cleanup."""
    expired = await delete_expired(session)
    decayed = await decay_low_importance(session)
    logger.info("api.maintenance_run", expired=expired, decayed=decayed)
    return {"expired_deleted": expired, "decayed": decayed}


# ---------------------------------------------------------------------------
# Working memory — per-session layer-1 cache (debugging / inspection)
# ---------------------------------------------------------------------------


@router.get("/working/{session_id}")
async def get_working_memory_state(session_id: str) -> Dict[str, Any]:
    """Return the live working-memory snapshot for a session.

    Useful to debug what the prompt builder sees in the
    "【当前对话状态】" section without having to dump the whole turn
    pipeline. Empty payload (turn_count=0) is a perfectly normal state
    for a session that has not produced any turns yet in this process.
    """
    wm = get_working_memory()
    state = await wm.snapshot(session_id)
    return state.to_dict()


@router.delete("/working/{session_id}")
async def clear_working_memory_state(session_id: str) -> Dict[str, bool]:
    """Wipe working memory for a session (also clears short-term backend)."""
    wm = get_working_memory()
    await wm.clear(session_id)
    logger.info("api.working_memory_cleared", session_id=session_id)
    return {"cleared": True}
