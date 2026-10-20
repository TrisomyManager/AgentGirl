"""Vector memory storage and similarity search using pgvector or SQLite fallback."""

import hashlib
import json
import struct
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from memory_system.graph_index import delete_graph_index, index_entry
from memory_system.graph_lifecycle import GraphMemoryDeletionORM, cleanup_locked, graph_lock
from memory_system.lifecycle import (
    StaleMemoryWriteError,
    capture_memory_epoch,
    decorate_entries,
    delete_lifecycle,
    ensure_state,
    lock_memory_epoch,
)
from shared_contracts.models import MemoryCategory, MemoryEntry
from shared_runtime.config import get_settings
from shared_runtime.llm_client import get_runtime_llm_config
from shared_runtime.model_presets import EMBEDDING_DIM, EMBEDDING_MODEL

logger = structlog.get_logger(__name__)

settings = get_settings()

# Ark embeddings use a dedicated model, endpoint and dimension independent of chat.
# The 1024-dimensional reduction fits pgvector IVFFlat indexes.
LOCAL_FALLBACK_DIM = EMBEDDING_DIM


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors in Python."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _resolve_embedding_config() -> tuple[str | None, str, str, int]:
    """Resolve (api_key, base_url, model, dim) from runtime config + settings."""
    rt = get_runtime_llm_config()
    host = urlparse(rt.get("openai_base_url") or "").hostname or ""
    runtime_ark = rt.get("provider") == "volcengine" or host.endswith(".volces.com")
    runtime_key = rt.get("openai_api_key") if runtime_ark else None
    return (
        settings.embedding_api_key or runtime_key or settings.ark_api_key,
        (settings.embedding_base_url or settings.ark_base_url).rstrip("/"),
        settings.embedding_model or EMBEDDING_MODEL,
        settings.embedding_dim,
    )


def resolve_embedding_dim() -> int:
    """Public helper: return the embedding dim for the current provider."""
    return _resolve_embedding_config()[3]


def _local_fallback_embedding(text_content: str, dim: int = LOCAL_FALLBACK_DIM) -> list[float]:
    """Deterministic hash-based pseudo-embedding for offline dev / no API key.

    Generates a unit-normalized float vector seeded from SHA-256 of the input.
    Not semantically meaningful but stable for dedup/exact-match lookups.
    """
    digest = hashlib.sha256(text_content.encode("utf-8")).digest()
    # Stretch the 32-byte digest into `dim` floats by chained hashing
    out: list[float] = []
    seed = digest
    while len(out) < dim:
        for i in range(0, len(seed), 4):
            if len(out) >= dim:
                break
            chunk = seed[i : i + 4].ljust(4, b"\0")
            (val,) = struct.unpack("<I", chunk)
            out.append((val / 0xFFFFFFFF) * 2.0 - 1.0)
        seed = hashlib.sha256(seed).digest()
    # Unit normalize
    norm = sum(v * v for v in out) ** 0.5 or 1.0
    return [v / norm for v in out]


async def _get_embedding(text_content: str) -> list[float]:
    """Fetch embedding via OpenAI-compatible /embeddings endpoint.

    Uses the dedicated Ark memory model, independent of the chat provider.
    Falls back to a hash-based pseudo-embedding when no API key is configured.
    """
    api_key, base_url, model, dim = _resolve_embedding_config()

    if not api_key:
        logger.warning("vector_store.no_api_key.using_local_fallback")
        return _local_fallback_embedding(text_content, dim)

    payload: dict = {"input": text_content, "model": model}
    multimodal = model.startswith("doubao-embedding-vision") or (
        "volces.com" in base_url and not model.startswith("doubao-embedding-large-text")
    )
    if multimodal:
        payload.update(input=[{"type": "text", "text": text_content}], dimensions=dim, encoding_format="float")
    # `dimensions` only honored by OpenAI text-embedding-3-* family.
    if "openai.com" in base_url and "text-embedding-3" in model:
        payload["dimensions"] = dim

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/embeddings" + ("/multimodal" if multimodal else ""),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            embedding = data["data"]["embedding"] if multimodal else data["data"][0]["embedding"]
            if len(embedding) != dim:
                raise ValueError(f"Expected {dim} embedding dimensions, received {len(embedding)}")
            return embedding
    except Exception as exc:
        logger.warning("vector_store.embedding_call_failed", error=str(exc), model=model)
        return _local_fallback_embedding(text_content, dim)


async def store_memory(
    session: AsyncSession,
    entry: MemoryEntry,
    *, extracted: dict | None = None,
    expected_epoch: int | None = None,
) -> MemoryEntry:
    """Store a memory entry with embedding into pgvector or SQLite."""
    if expected_epoch is None:
        expected_epoch = await capture_memory_epoch(entry.user_id)
    embedding = entry.embedding
    if embedding is None:
        embedding = await _get_embedding(entry.content)
        entry.embedding = embedding

    if not await lock_memory_epoch(session, entry.user_id, expected=expected_epoch):
        await session.rollback()
        raise StaleMemoryWriteError("Memory was cleared while this write was in progress")
    memory_id = str(uuid.uuid4())

    if settings.lite_mode:
        # SQLite: store embedding as JSON string
        embedding_json = json.dumps(embedding)
        await session.execute(
            text(
                """
                INSERT INTO memories (
                    id, user_id, category, content, importance,
                    emotion_tags, embedding, source_turn_id, created_at, expires_at
                ) VALUES (
                    :id, :user_id, :category, :content, :importance,
                    :emotion_tags, :embedding, :source_turn_id, :created_at, :expires_at
                )
                """
            ),
            {
                "id": memory_id,
                "user_id": entry.user_id,
                "category": entry.category.value,
                "content": entry.content,
                "importance": entry.importance,
                "emotion_tags": json.dumps([tag.value for tag in entry.emotion_tags]),
                "embedding": embedding_json,
                "source_turn_id": entry.source_turn_id,
                "created_at": entry.created_at or datetime.utcnow(),
                "expires_at": entry.expires_at,
            },
        )
    else:
        # PostgreSQL + pgvector: use ::vector cast
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        await session.execute(
            text(
                """
                INSERT INTO memories (
                    id, user_id, category, content, importance,
                    emotion_tags, embedding, source_turn_id, created_at, expires_at
                ) VALUES (
                    :id, :user_id, :category, :content, :importance,
                    CAST(:emotion_tags AS json), CAST(:embedding AS vector), :source_turn_id, :created_at, :expires_at
                )
                """
            ),
            {
                "id": memory_id,
                "user_id": entry.user_id,
                "category": entry.category.value,
                "content": entry.content,
                "importance": entry.importance,
                "emotion_tags": json.dumps([tag.value for tag in entry.emotion_tags]),
                "embedding": embedding_str,
                "source_turn_id": entry.source_turn_id,
                "created_at": entry.created_at or datetime.utcnow(),
                "expires_at": entry.expires_at,
            },
        )

    entry.entry_id = str(memory_id)
    await ensure_state(session, entry)
    await index_entry(session, entry, extracted)
    await session.commit()
    logger.info(
        "vector_store.stored",
        memory_id=str(memory_id),
        user_id=entry.user_id,
        category=entry.category.value,
    )
    return entry


async def search_similar(
    session: AsyncSession,
    user_id: str,
    query: str,
    top_k: int = 5,
    category: MemoryCategory | None = None,
    min_importance: float | None = None,
    include_dormant: bool = False,
) -> list[MemoryEntry]:
    """Vector similarity search using cosine distance (pgvector) or Python fallback (SQLite)."""
    embedding = await _get_embedding(query)

    if settings.lite_mode:
        # SQLite: fetch all user memories and compute similarity in Python
        filters = ["user_id = :user_id"]
        params: dict = {"user_id": user_id}
        if not include_dormant:
            filters.append("(expires_at IS NULL OR expires_at > :active_at)")
            params["active_at"] = datetime.utcnow()

        if category:
            filters.append("category = :category")
            params["category"] = category.value
        if min_importance is not None:
            filters.append("importance >= :min_importance")
            params["min_importance"] = min_importance

        where_clause = " AND ".join(filters)

        result = await session.execute(
            text(
                f"""
                SELECT
                    id, user_id, category, content, importance,
                    emotion_tags, source_turn_id, created_at, expires_at,
                    embedding
                FROM memories
                WHERE {where_clause}
                """
            ),
            params,
        )

        rows = result.mappings().all()
        scored = []
        for row in rows:
            # Parse JSON embedding from SQLite Text column
            row_embedding = row["embedding"]
            if row_embedding is None:
                continue
            if isinstance(row_embedding, str):
                try:
                    row_embedding = json.loads(row_embedding)
                except json.JSONDecodeError:
                    continue
            if not isinstance(row_embedding, list) or len(row_embedding) != len(embedding):
                continue
            similarity = _cosine_similarity(embedding, row_embedding)
            scored.append((similarity, row))

        # Sort by similarity descending, take top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        top_rows = scored[:top_k]

        entries: list[MemoryEntry] = []
        for similarity, row in top_rows:
            # Parse emotion_tags from JSON string in SQLite
            emotion_tags_raw = row["emotion_tags"]
            if isinstance(emotion_tags_raw, str):
                try:
                    emotion_tags_raw = json.loads(emotion_tags_raw)
                except json.JSONDecodeError:
                    emotion_tags_raw = []
            entries.append(
                MemoryEntry(
                    entry_id=str(row["id"]),
                    user_id=row["user_id"],
                    category=MemoryCategory(row["category"]),
                    content=row["content"],
                    importance=row["importance"],
                    emotion_tags=list(emotion_tags_raw) if emotion_tags_raw else [],
                    source_turn_id=row["source_turn_id"],
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                    similarity=max(-1.0, min(1.0, similarity)),
                )
            )
        logger.info(
            "vector_store.searched_lite",
            user_id=user_id,
            query=query[:50],
            results=len(entries),
        )
        return await decorate_entries(session, user_id, entries)

    # PostgreSQL + pgvector: use native vector operators
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    filters = ["user_id = :user_id"]
    params = {
        "user_id": user_id,
        "embedding": embedding_str,
        "top_k": top_k,
    }
    if not include_dormant:
        filters.append("(expires_at IS NULL OR expires_at > :active_at)")
        params["active_at"] = datetime.utcnow()

    if category:
        filters.append("category = :category")
        params["category"] = category.value
    if min_importance is not None:
        filters.append("importance >= :min_importance")
        params["min_importance"] = min_importance

    where_clause = " AND ".join(filters)

    result = await session.execute(
        text(
            f"""
            SELECT
                id, user_id, category, content, importance,
                emotion_tags, source_turn_id, created_at, expires_at,
                embedding <=> CAST(:embedding AS vector) AS distance
            FROM memories
            WHERE {where_clause}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
            """
        ),
        params,
    )

    rows = result.mappings().all()
    entries = []
    for row in rows:
        tags = row["emotion_tags"] or []
        if isinstance(tags, str):
            tags = json.loads(tags)
        entries.append(
            MemoryEntry(
                entry_id=str(row["id"]),
                user_id=row["user_id"],
                category=MemoryCategory(row["category"]),
                content=row["content"],
                importance=row["importance"],
                emotion_tags=tags,
                source_turn_id=row["source_turn_id"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                similarity=max(-1.0, min(1.0, 1.0 - float(row["distance"]))),
            )
        )
    logger.info(
        "vector_store.searched",
        user_id=user_id,
        query=query[:50],
        results=len(entries),
    )
    return await decorate_entries(session, user_id, entries)


async def delete_expired(session: AsyncSession) -> int:
    """Delete memories past their expiration date."""
    result = await session.execute(
        text(
            """
            DELETE FROM memories
            WHERE expires_at IS NOT NULL AND expires_at < :now
            """
        ),
        {"now": datetime.utcnow()},
    )
    await session.commit()
    deleted = result.rowcount or 0
    logger.info("vector_store.expired_deleted", count=deleted)
    return deleted


async def decay_low_importance(
    session: AsyncSession,
    threshold: float = 0.2,
    decay_days: int = 30,
) -> int:
    """Reduce importance of old, low-importance memories and set expiration."""
    cutoff = datetime.utcnow() - timedelta(days=decay_days)
    result = await session.execute(
        text(
            """
            UPDATE memories
            SET importance = importance * 0.9,
                expires_at = COALESCE(expires_at, :expires_at)
            WHERE importance < :threshold
              AND created_at < :cutoff
              AND (expires_at IS NULL OR expires_at > :now)
            """
        ),
        {
            "threshold": threshold,
            "cutoff": cutoff,
            "expires_at": datetime.utcnow() + timedelta(days=7),
            "now": datetime.utcnow(),
        },
    )
    await session.commit()
    updated = result.rowcount or 0
    logger.info("vector_store.decay_applied", count=updated)
    return updated


async def list_user_memories(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    category: MemoryCategory | None = None,
) -> list[MemoryEntry]:
    """List a user's memories ordered by created_at desc, with optional category filter."""
    filters = ["user_id = :user_id"]
    params: dict = {"user_id": user_id, "limit": limit, "offset": offset}
    if category:
        filters.append("category = :category")
        params["category"] = category.value
    where_clause = " AND ".join(filters)

    result = await session.execute(
        text(
            f"""
            SELECT
                id, user_id, category, content, importance,
                emotion_tags, source_turn_id, created_at, expires_at
            FROM memories
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )
    rows = result.mappings().all()
    entries: list[MemoryEntry] = []
    for row in rows:
        emotion_tags_raw = row["emotion_tags"]
        if isinstance(emotion_tags_raw, str):
            try:
                emotion_tags_raw = json.loads(emotion_tags_raw)
            except json.JSONDecodeError:
                emotion_tags_raw = []
        entries.append(
            MemoryEntry(
                entry_id=str(row["id"]),
                user_id=row["user_id"],
                category=MemoryCategory(row["category"]),
                content=row["content"],
                importance=row["importance"],
                emotion_tags=list(emotion_tags_raw or []),
                source_turn_id=row["source_turn_id"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
            )
        )
    return await decorate_entries(session, user_id, entries)


async def delete_user_memories(session: AsyncSession, user_id: str, *, commit: bool = True) -> int:
    """Delete all memories for a user. Returns count deleted."""
    result = await session.execute(
        text("DELETE FROM memories WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    await delete_lifecycle(session, user_id=user_id)
    await delete_graph_index(session, user_id=user_id)
    if commit:
        await session.commit()
    deleted = result.rowcount or 0
    logger.info("vector_store.user_memories_deleted", user_id=user_id, count=deleted)
    return deleted


async def delete_memory_by_id(session: AsyncSession, memory_id: str) -> bool:
    """Delete a single memory by id."""
    try:
        memory_id = str(uuid.UUID(memory_id))
    except (ValueError, TypeError, AttributeError):
        return False
    owner = await session.scalar(text("SELECT user_id FROM memories WHERE id = :id"), {"id": memory_id})
    if owner is None:
        return False
    async with graph_lock(owner):
        result = await session.execute(text("DELETE FROM memories WHERE id = :id AND user_id = :user"),
                                       {"id": memory_id, "user": owner})
        await delete_lifecycle(session, memory_id=memory_id)
        await delete_graph_index(session, memory_id=memory_id)
        if settings.enable_knowledge_graph and not settings.lite_mode:
            await session.merge(GraphMemoryDeletionORM(user_id=owner, memory_id=memory_id))
        await session.commit()
        await cleanup_locked(owner)
    return (result.rowcount or 0) > 0


async def get_user_memory_summary(session: AsyncSession, user_id: str) -> dict:
    """Return aggregate stats for a user's memories."""
    result = await session.execute(
        text(
            """
            SELECT
                COUNT(*) AS total,
                AVG(importance) AS avg_importance,
                MAX(created_at) AS last_memory,
                category
            FROM memories
            WHERE user_id = :user_id
            GROUP BY category
            """
        ),
        {"user_id": user_id},
    )
    rows = result.mappings().all()
    summary = {
        "total_memories": sum(r["total"] for r in rows),
        "avg_importance": (
            sum(r["avg_importance"] * r["total"] for r in rows) / sum(r["total"] for r in rows)
            if rows else 0.0
        ),
        "last_memory": max((r["last_memory"] for r in rows), default=None),
        "by_category": {r["category"]: r["total"] for r in rows},
    }
    return summary
