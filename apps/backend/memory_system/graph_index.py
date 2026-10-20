"""User-scoped entity graph and personalized PageRank for memory retrieval.

The relational graph works in Lite and PostgreSQL modes. Neo4j remains an optional
adapter; remembering related events never depends on a graph server being present.
"""

import math
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, cast, delete, or_, select

from memory_system.db import MemoryORM
from memory_system.lifecycle import decorate_entries
from shared_contracts.models import MemoryEntry
from shared_runtime.database import Base


class MemoryEntityLinkORM(Base):
    __tablename__ = "memory_entity_links"
    memory_id = Column(String(64), primary_key=True)
    label = Column(String(200), primary_key=True)
    user_id = Column(String(128), nullable=False, index=True)
    kind = Column(String(32), nullable=False, default="entity")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class MemoryRelationORM(Base):
    __tablename__ = "memory_relations"
    memory_id = Column(String(64), primary_key=True)
    source = Column(String(200), primary_key=True)
    target = Column(String(200), primary_key=True)
    relation = Column(String(64), primary_key=True)
    user_id = Column(String(128), nullable=False, index=True)


class MemoryGraphIndexORM(Base):
    __tablename__ = "memory_graph_index_versions"
    memory_id = Column(String(64), primary_key=True)
    user_id = Column(String(128), nullable=False, index=True)


_STOPWORDS = {
    "用户",
    "助手",
    "我们",
    "你们",
    "一个",
    "这个",
    "那个",
    "今天",
    "现在",
    "喜欢",
    "记得",
    "最近",
    "什么",
    "the",
    "and",
    "that",
    "user",
    "assistant",
}


def keywords(text: str) -> set[str]:
    tokens = {word.lower() for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,39}", text)}
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.update(phrase[i : i + 2] for i in range(len(phrase) - 1))
    return {token for token in tokens if token not in _STOPWORDS}


async def index_entry(session, entry: MemoryEntry, extracted: dict | None = None) -> None:
    if session.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    extracted = extracted or {}
    labels = {}
    for entity in extracted.get("entities", [])[:48]:
        label = str(entity.get("name") or "").strip().lower()[:200]
        if label:
            labels[label] = str(entity.get("type") or "entity")[:32]
    relationships = []
    for relation in extracted.get("relationships", [])[:64]:
        source = str(relation.get("source") or "").strip().lower()[:200]
        target = str(relation.get("target") or "").strip().lower()[:200]
        if not source or not target:
            continue
        labels.setdefault(source, "entity")
        labels.setdefault(target, "entity")
        relationships.append(
            {
                "memory_id": entry.entry_id,
                "user_id": entry.user_id,
                "source": source,
                "target": target,
                "relation": str(relation.get("type") or "RELATED_TO")[:64],
            }
        )
    # Lexical anchors complement extracted entities and provide offline retrieval.
    for label in sorted(keywords(entry.content))[:80]:
        labels.setdefault(label, "keyword")
    if labels:
        await session.execute(
            insert(MemoryEntityLinkORM)
            .values(
                [
                    {"memory_id": entry.entry_id, "user_id": entry.user_id, "label": label, "kind": kind}
                    for label, kind in labels.items()
                ]
            )
            .on_conflict_do_nothing()
        )
    if relationships:
        await session.execute(insert(MemoryRelationORM).values(relationships).on_conflict_do_nothing())
    await session.execute(
        insert(MemoryGraphIndexORM)
        .values(
            memory_id=entry.entry_id,
            user_id=entry.user_id,
        )
        .on_conflict_do_nothing(index_elements=["memory_id"])
    )


async def backfill_graph(session, batch_size: int = 200) -> int:
    rows = (
        (
            await session.execute(
                select(MemoryORM)
                .outerjoin(
                    MemoryGraphIndexORM,
                    cast(MemoryORM.id, String) == MemoryGraphIndexORM.memory_id,
                )
                .where(MemoryGraphIndexORM.memory_id.is_(None))
                .order_by(MemoryORM.created_at.desc())
                .limit(batch_size)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        await index_entry(
            session,
            MemoryEntry(
                entry_id=str(row.id),
                user_id=row.user_id,
                content=row.content,
                category=row.category,
                importance=row.importance,
            ),
        )
    await session.commit()
    return len(rows)


def personalized_pagerank(
    adjacency: dict, seeds: dict[str, float], iterations: int = 30, restart: float = 0.2
) -> dict[str, float]:
    seeds = {key: value for key, value in seeds.items() if key in adjacency and value > 0}
    total = sum(seeds.values())
    if not total:
        return {}
    seeds = {key: value / total for key, value in seeds.items()}
    scores = dict(seeds)
    for _ in range(iterations):
        following = defaultdict(float, {key: restart * value for key, value in seeds.items()})
        dangling = 0.0
        for node, mass in scores.items():
            neighbors = adjacency.get(node, {})
            weight_sum = sum(neighbors.values())
            if not weight_sum:
                dangling += (1 - restart) * mass
                continue
            for neighbor, weight in neighbors.items():
                following[neighbor] += (1 - restart) * mass * weight / weight_sum
        for node, weight in seeds.items():
            following[node] += dangling * weight
        scores = dict(following)
    return scores


async def graph_candidates(
    session,
    user_id: str,
    query: str,
    semantic: list[MemoryEntry],
    *,
    top_k=20,
    category=None,
    min_importance=None,
    include_dormant=False,
    facts_with_sources=False,
) -> tuple[list[MemoryEntry], list]:
    statement = (
        select(MemoryEntityLinkORM)
        .join(
            MemoryORM,
            cast(MemoryORM.id, String) == MemoryEntityLinkORM.memory_id,
        )
        .where(MemoryEntityLinkORM.user_id == user_id, MemoryORM.user_id == user_id)
    )
    if not include_dormant:
        statement = statement.where(or_(MemoryORM.expires_at.is_(None), MemoryORM.expires_at > datetime.now(UTC)))
    if category is not None:
        statement = statement.where(MemoryORM.category == category.value)
    if min_importance is not None:
        statement = statement.where(MemoryORM.importance >= min_importance)
    links = (
        (await session.execute(statement.order_by(MemoryEntityLinkORM.created_at.desc()).limit(6000))).scalars().all()
    )
    if not links:
        return [], []
    degrees = Counter(link.label for link in links)
    adjacency = defaultdict(dict)
    seeds = {}
    normalized_query = query.lower().strip()
    query_words = keywords(query)
    for link in links:
        memory, entity = f"m:{link.memory_id}", f"e:{link.label}"
        weight = 1 / math.log2(2 + degrees[link.label])
        adjacency[memory][entity] = weight
        adjacency[entity][memory] = weight
        if link.label in query_words or (link.kind != "keyword" and link.label in normalized_query):
            seeds[entity] = 1.0
    for entry in semantic:
        if entry.similarity is not None and entry.similarity >= 0.18:
            seeds[f"m:{entry.entry_id}"] = max(0.0, entry.similarity) * 0.5
    relations = (
        (
            await session.execute(
                select(MemoryRelationORM)
                .where(
                    MemoryRelationORM.user_id == user_id,
                    MemoryRelationORM.memory_id.in_({link.memory_id for link in links}),
                )
                .limit(2000)
            )
        )
        .scalars()
        .all()
    )
    for relation in relations:
        source, target = f"e:{relation.source}", f"e:{relation.target}"
        if source in adjacency and target in adjacency:
            adjacency[source][target] = 1.0
            adjacency[target][source] = 1.0
    scores = personalized_pagerank(adjacency, seeds)
    ranked_ids = sorted(
        (node[2:] for node in scores if node.startswith("m:")),
        key=lambda identity: scores[f"m:{identity}"],
        reverse=True,
    )[:top_k]
    if not ranked_ids:
        return [], []
    memories = (
        (
            await session.execute(
                select(MemoryORM).where(
                    MemoryORM.user_id == user_id,
                    cast(MemoryORM.id, String).in_(ranked_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    entries = {
        str(row.id): MemoryEntry(
            entry_id=str(row.id),
            user_id=row.user_id,
            category=row.category,
            content=row.content,
            importance=row.importance,
            emotion_tags=row.emotion_tags or [],
            source_turn_id=row.source_turn_id,
            created_at=row.created_at,
            expires_at=row.expires_at,
        )
        for row in memories
    }
    decorated = await decorate_entries(session, user_id, [entries[key] for key in ranked_ids if key in entries])
    eligible_ids = {entry.entry_id for entry in decorated if include_dormant or entry.memory_status == "active"}
    facts = [
        (rel.memory_id, f"{rel.source} — {rel.relation} — {rel.target}")
        for rel in relations
        if rel.memory_id in eligible_ids and (f"e:{rel.source}" in seeds or f"e:{rel.target}" in seeds)
    ]
    if facts_with_sources:
        return decorated, [{"memory_id": memory_id, "text": text} for memory_id, text in dict.fromkeys(facts)][:10]
    return decorated, list(dict.fromkeys(text for _, text in facts))[:10]


async def delete_graph_index(session, *, user_id: str | None = None, memory_id: str | None = None) -> None:
    for model in (MemoryEntityLinkORM, MemoryRelationORM, MemoryGraphIndexORM):
        statement = delete(model)
        if user_id is not None:
            statement = statement.where(model.user_id == user_id)
        if memory_id is not None:
            statement = statement.where(model.memory_id == memory_id)
        await session.execute(statement)
