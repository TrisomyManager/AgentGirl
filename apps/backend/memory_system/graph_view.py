"""Bounded read-only projection of the user's SQL memory index for visualization."""

import hashlib
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import String, and_, cast, exists, func, or_, select

from memory_system.db import MemoryORM
from memory_system.graph_index import MemoryEntityLinkORM, MemoryRelationORM
from memory_system.lifecycle import MemoryStateORM, utc


def entity_id(label):
    return "e:" + hashlib.sha256(label.encode()).hexdigest()[:24]


async def memory_graph(session, user_id, *, limit=40, query="", include_dormant=False, include_keywords=False):
    limit = min(80, max(1, limit))
    memory_key = cast(MemoryORM.id, String)
    statement = (
        select(
            memory_key.label("id"),
            func.substr(MemoryORM.content, 1, 2001).label("content"),
            MemoryORM.category,
            MemoryORM.importance,
            MemoryORM.created_at,
            MemoryORM.expires_at,
            MemoryStateORM.dormant_since,
            MemoryStateORM.effective_importance,
        )
        .outerjoin(MemoryStateORM, and_(MemoryStateORM.memory_id == memory_key, MemoryStateORM.user_id == user_id))
        .where(MemoryORM.user_id == user_id)
    )
    if not include_dormant:
        statement = statement.where(
            MemoryStateORM.dormant_since.is_(None),
            or_(MemoryORM.expires_at.is_(None), MemoryORM.expires_at > datetime.now(UTC)),
        )
    query = query.strip()[:120]
    if query:
        statement = statement.where(
            or_(
                MemoryORM.content.icontains(query, autoescape=True),
                exists(
                    select(MemoryEntityLinkORM.memory_id).where(
                        MemoryEntityLinkORM.memory_id == memory_key,
                        MemoryEntityLinkORM.user_id == user_id,
                        MemoryEntityLinkORM.label.icontains(query, autoescape=True),
                    )
                ),
            )
        )
    rows = (await session.execute(statement.order_by(MemoryORM.created_at.desc(), MemoryORM.id).limit(limit + 1))).all()
    truncated = len(rows) > limit
    rows = rows[:limit]
    ids = [row.id for row in rows]
    nodes, edges = [], []
    now = datetime.now(UTC)
    for row in rows:
        dormant = bool(row.dormant_since or (row.expires_at and utc(row.expires_at) <= now))
        nodes.append(
            {
                "id": "m:" + row.id,
                "kind": "memory",
                "label": row.content[:32],
                "memory_id": row.id,
                "content": row.content[:2000],
                "content_truncated": len(row.content) > 2000,
                "category": row.category,
                "status": "dormant" if dormant else "active",
                "importance": row.effective_importance if row.effective_importance is not None else row.importance,
                "created_at": utc(row.created_at).isoformat() if row.created_at else None,
            }
        )
    if not ids:
        return {"nodes": [], "edges": [], "truncated": False, "memory_count": 0, "source": "sql_index"}
    links_statement = select(MemoryEntityLinkORM).where(
        MemoryEntityLinkORM.user_id == user_id,
        MemoryEntityLinkORM.memory_id.in_(ids),
    )
    if not include_keywords:
        links_statement = links_statement.where(MemoryEntityLinkORM.kind != "keyword")
    links = (
        (
            await session.execute(
                links_statement.order_by(
                    MemoryEntityLinkORM.kind, MemoryEntityLinkORM.label, MemoryEntityLinkORM.memory_id
                ).limit(12001)
            )
        )
        .scalars()
        .all()
    )
    truncated = truncated or len(links) > 12000
    counts = Counter(link.label for link in links)
    kinds = {}
    for link in links:
        if link.label not in kinds or link.kind != "keyword":
            kinds[link.label] = link.kind
    labels = sorted(counts, key=lambda label: (kinds[label] == "keyword", -counts[label], label))[:60]
    truncated = truncated or len(counts) > len(labels)
    selected = set(labels)
    for label in labels:
        nodes.append(
            {
                "id": entity_id(label),
                "kind": "keyword" if kinds[label] == "keyword" else "entity",
                "label": label,
                "entity_type": kinds[label],
            }
        )
    mentions = sorted(links, key=lambda link: (link.kind == "keyword", -counts[link.label], link.label, link.memory_id))
    for link in mentions:
        if link.label in selected:
            if len(edges) >= 400:
                truncated = True
                break
            edges.append(
                {
                    "source": "m:" + link.memory_id,
                    "target": entity_id(link.label),
                    "kind": "mentions",
                    "label": "提及",
                    "memory_ids": [link.memory_id],
                }
            )
    # Relations remain grounded in visible memory evidence; orphan/other-user index rows never appear.
    relations = (
        (
            await session.execute(
                select(MemoryRelationORM)
                .where(
                    MemoryRelationORM.user_id == user_id,
                    MemoryRelationORM.memory_id.in_(ids),
                    MemoryRelationORM.source.in_(labels),
                    MemoryRelationORM.target.in_(labels),
                )
                .order_by(MemoryRelationORM.source, MemoryRelationORM.target, MemoryRelationORM.relation)
                .limit(1001)
            )
        )
        .scalars()
        .all()
    )
    grouped = {}
    for relation in relations[:1000]:
        key = (relation.source, relation.target, relation.relation)
        grouped.setdefault(key, set()).add(relation.memory_id)
    for (source, target, label), evidence in list(grouped.items())[:100]:
        edges.append(
            {
                "source": entity_id(source),
                "target": entity_id(target),
                "kind": "relation",
                "label": label,
                "memory_ids": sorted(evidence),
            }
        )
    return {
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated or len(relations) > 1000 or len(grouped) > 100,
        "memory_count": len(rows),
        "source": "sql_index",
    }
