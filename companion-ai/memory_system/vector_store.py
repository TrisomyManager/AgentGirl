"""Vector memory storage and similarity search using pgvector or SQLite fallback."""

import hashlib
import json
import struct
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from shared.config import get_settings
from shared.llm_client import get_runtime_llm_config
from shared.models import MemoryCategory, MemoryEntry

from memory_system.db import MemoryORM

logger = structlog.get_logger(__name__)

settings = get_settings()

# Default embedding dimension (matches OpenAI text-embedding-3-small).
# DashScope text-embedding-v3 is 1024-dim; SiliconFlow BGE-M3 is also 1024-dim.
# In lite_mode (SQLite + JSON storage) the dim is flexible; in PostgreSQL the
# table column is fixed at create time so a single dim must be chosen there.
EMBEDDING_DIM = 1536
EMBEDDING_MODEL = "text-embedding-3-small"
LOCAL_FALLBACK_DIM = 384  # used when no API key configured


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors in Python."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _resolve_embedding_config() -> Tuple[Optional[str], str, str, int]:
    """Resolve (api_key, base_url, model, dim) from runtime config + settings."""
    rt = get_runtime_llm_config()
    api_key = rt.get("openai_api_key") or settings.openai_api_key
    base_url = (
        rt.get("openai_base_url") or settings.openai_base_url or "https://api.openai.com/v1"
    ).rstrip("/")
    base_lower = base_url.lower()
    if "dashscope" in base_lower or "aliyuncs" in base_lower:
        model = "text-embedding-v3"
        dim = 1024
    elif "siliconflow" in base_lower:
        model = "BAAI/bge-m3"
        dim = 1024
    else:
        model = EMBEDDING_MODEL
        dim = EMBEDDING_DIM
    return api_key, base_url, model, dim


def resolve_embedding_dim() -> int:
    """Public helper: return the embedding dim for the current provider."""
    return _resolve_embedding_config()[3]


def _local_fallback_embedding(text_content: str, dim: int = LOCAL_FALLBACK_DIM) -> List[float]:
    """Deterministic hash-based pseudo-embedding for offline dev / no API key.

    Generates a unit-normalized float vector seeded from SHA-256 of the input.
    Not semantically meaningful but stable for dedup/exact-match lookups.
    """
    digest = hashlib.sha256(text_content.encode("utf-8")).digest()
    # Stretch the 32-byte digest into `dim` floats by chained hashing
    out: List[float] = []
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


async def _get_embedding(text_content: str) -> List[float]:
    """Fetch embedding via OpenAI-compatible /embeddings endpoint.

    Auto-detects model + dim from base_url (OpenAI / DashScope / SiliconFlow).
    Falls back to a hash-based pseudo-embedding when no API key is configured.
    """
    api_key, base_url, model, dim = _resolve_embedding_config()

    if not api_key:
        logger.warning("vector_store.no_api_key.using_local_fallback")
        return _local_fallback_embedding(text_content)

    payload: dict = {"input": text_content, "model": model}
    # `dimensions` only honored by OpenAI text-embedding-3-* family.
    if "openai.com" in base_url and "text-embedding-3" in model:
        payload["dimensions"] = dim

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except Exception as exc:
        logger.warning("vector_store.embedding_call_failed", error=str(exc), model=model)
        return _local_fallback_embedding(text_content)


async def store_memory(
    session: AsyncSession,
    entry: MemoryEntry,
) -> MemoryEntry:
    """Store a memory entry with embedding into pgvector or SQLite."""
    embedding = entry.embedding
    if embedding is None:
        embedding = await _get_embedding(entry.content)
        entry.embedding = embedding

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
                    :emotion_tags, :embedding::vector, :source_turn_id, :created_at, :expires_at
                )
                """
            ),
            {
                "id": memory_id,
                "user_id": entry.user_id,
                "category": entry.category.value,
                "content": entry.content,
                "importance": entry.importance,
                "emotion_tags": [tag.value for tag in entry.emotion_tags],
                "embedding": embedding_str,
                "source_turn_id": entry.source_turn_id,
                "created_at": entry.created_at or datetime.utcnow(),
                "expires_at": entry.expires_at,
            },
        )

    await session.commit()
    entry.entry_id = str(memory_id)
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
    category: Optional[MemoryCategory] = None,
    min_importance: Optional[float] = None,
) -> List[MemoryEntry]:
    """Vector similarity search using cosine distance (pgvector) or Python fallback (SQLite)."""
    embedding = await _get_embedding(query)

    if settings.lite_mode:
        # SQLite: fetch all user memories and compute similarity in Python
        filters = ["user_id = :user_id"]
        params: dict = {"user_id": user_id}

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
            if not isinstance(row_embedding, list):
                continue
            similarity = _cosine_similarity(embedding, row_embedding)
            scored.append((similarity, row))

        # Sort by similarity descending, take top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        top_rows = [row for _, row in scored[:top_k]]

        entries: List[MemoryEntry] = []
        for row in top_rows:
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
                    emotion_tags=[tag for tag in emotion_tags_raw] if emotion_tags_raw else [],
                    source_turn_id=row["source_turn_id"],
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                )
            )
        logger.info(
            "vector_store.searched_lite",
            user_id=user_id,
            query=query[:50],
            results=len(entries),
        )
        return entries

    # PostgreSQL + pgvector: use native vector operators
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    filters = ["user_id = :user_id"]
    params = {
        "user_id": user_id,
        "embedding": embedding_str,
        "top_k": top_k,
    }

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
                embedding <=> :embedding::vector AS distance
            FROM memories
            WHERE {where_clause}
            ORDER BY embedding <=> :embedding::vector
            LIMIT :top_k
            """
        ),
        params,
    )

    rows = result.mappings().all()
    entries = []
    for row in rows:
        entries.append(
            MemoryEntry(
                entry_id=str(row["id"]),
                user_id=row["user_id"],
                category=MemoryCategory(row["category"]),
                content=row["content"],
                importance=row["importance"],
                emotion_tags=[tag for tag in row["emotion_tags"]],
                source_turn_id=row["source_turn_id"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
            )
        )
    logger.info(
        "vector_store.searched",
        user_id=user_id,
        query=query[:50],
        results=len(entries),
    )
    return entries


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
    category: Optional[MemoryCategory] = None,
) -> List[MemoryEntry]:
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
    entries: List[MemoryEntry] = []
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
                emotion_tags=[tag for tag in (emotion_tags_raw or [])],
                source_turn_id=row["source_turn_id"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
            )
        )
    return entries


async def delete_user_memories(session: AsyncSession, user_id: str) -> int:
    """Delete all memories for a user. Returns count deleted."""
    result = await session.execute(
        text("DELETE FROM memories WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    await session.commit()
    deleted = result.rowcount or 0
    logger.info("vector_store.user_memories_deleted", user_id=user_id, count=deleted)
    return deleted


async def delete_memory_by_id(session: AsyncSession, memory_id: str) -> bool:
    """Delete a single memory by id."""
    result = await session.execute(
        text("DELETE FROM memories WHERE id = :id"),
        {"id": memory_id},
    )
    await session.commit()
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
