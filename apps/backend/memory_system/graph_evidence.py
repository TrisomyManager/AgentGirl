"""Immutable per-memory facts; no merged value can inherit another memory's evidence."""

import hashlib
import json


def identity(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def project_facts(user_id, memory_id, extracted):
    """Bound graph projections independently of provider output sizes."""
    facts = []

    def add(kind, text, *labels):
        text = text[:1500]
        labels = sorted({str(label)[:200] for label in labels if label})[:2]
        facts.append({"kind": kind, "text": text, "labels": labels})

    def encoded(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))[:1000]

    for item in (extracted.get("entities") or [])[:32]:
        name = str(item.get("name") or "")[:200]
        if name:
            suffix = " " + encoded(item["properties"]) if item.get("properties") else ""
            add("entity", f"User knows {item.get('type', 'generic')}: {name}{suffix}", name)
    for item in (extracted.get("relationships") or [])[:32]:
        source, target = item.get("source"), item.get("target")
        if source and target:
            add("relation", f"{source} — {item.get('type', 'RELATED_TO')} — {target}", source, target)
    for item in (extracted.get("events") or [])[:16]:
        if name := item.get("name"):
            add("event", f"User experienced: {name} " + encoded(item.get("properties") or {}), name)
    for item in (extracted.get("preferences") or [])[:16]:
        if key := item.get("key"):
            add("preference", f"User prefers {key} = {encoded(item.get('value'))}", key)
    for item in (extracted.get("emotions") or [])[:16]:
        if tag := item.get("tag"):
            add("emotion", f"User felt {tag}: {str(item.get('trigger') or '')[:500]}", tag)
    unique = {identity(fact): fact for fact in facts}
    rows = []
    for key in sorted(unique)[:64]:
        fact = unique[key]
        rows.append(
            {
                **fact,
                "fact_id": identity(user_id, memory_id, key),
                "entities": [{"entity_id": identity(user_id, label), "label": label} for label in fact["labels"]],
            }
        )
    return rows


async def store(transaction, user_id, memory_id, facts, expected_epoch):
    fence = await transaction.run(
        "MERGE (g:GraphFence {owner_key:$key}) ON CREATE SET g.epoch=$epoch "
        "SET g._write_lock=true REMOVE g._write_lock RETURN g.epoch AS epoch",
        key=identity(user_id),
        epoch=expected_epoch,
    )
    if (await fence.single())["epoch"] != expected_epoch:
        raise ValueError("Graph write belongs to a cleared generation")
    evidence_id = identity(user_id, memory_id)
    digest = identity(facts)
    result = await transaction.run(
        "MERGE (u:User {user_id:$user}) "
        "MERGE (e:MemoryEvidence {evidence_id:$evidence_id}) "
        "ON CREATE SET e.user_id=$user,e.memory_id=$memory_id,e.digest=$digest,e.schema_version=1 "
        "RETURN e.user_id AS owner,e.memory_id AS memory_id,e.digest AS digest,e.deleted AS deleted",
        user=user_id,
        evidence_id=evidence_id,
        memory_id=memory_id,
        digest=digest,
    )
    existing = await result.single()
    if existing["deleted"] or (existing["owner"], existing["memory_id"], existing["digest"]) != (
        user_id,
        memory_id,
        digest,
    ):
        raise ValueError("Graph evidence is immutable; source reconciliation is required")
    result = await transaction.run(
        "MATCH (u:User {user_id:$user}),(e:MemoryEvidence {evidence_id:$evidence_id}) "
        "MERGE (u)-[:HAS_MEMORY]->(e) "
        "WITH e UNWIND $facts AS row "
        "MERGE (f:MemoryFact {fact_id:row.fact_id}) "
        "ON CREATE SET f.user_id=$user,f.memory_id=$memory_id,f.text=row.text,f.kind=row.kind "
        "MERGE (e)-[:SUPPORTS]->(f) "
        "WITH f,row UNWIND row.entities AS entity "
        "MERGE (n:MemoryEntity {entity_id:entity.entity_id}) "
        "ON CREATE SET n.user_id=$user,n.label=entity.label "
        "MERGE (f)-[:MENTIONS]->(n)",
        user=user_id,
        evidence_id=evidence_id,
        memory_id=memory_id,
        facts=facts,
    )
    await result.consume()


async def delete(transaction, user_id, memory_ids):
    # A source tombstone serializes even a delayed/cancelled server transaction.
    # It contains identifiers only and is removed by full-user graph erasure.
    result = await transaction.run(
        "UNWIND $sources AS source MERGE (e:MemoryEvidence {evidence_id:source.key}) "
        "ON CREATE SET e.user_id=$user,e.memory_id=source.id,e.schema_version=1 "
        "SET e.deleted=true REMOVE e.digest",
        user=user_id,
        sources=[{"key": identity(user_id, memory_id), "id": memory_id} for memory_id in memory_ids],
    )
    await result.consume()
    result = await transaction.run(
        "MATCH (n) WHERE n.user_id=$user AND n.memory_id IN $memory_ids AND n:MemoryFact DETACH DELETE n",
        user=user_id,
        memory_ids=memory_ids,
    )
    await result.consume()
    result = await transaction.run(
        "MATCH (n:MemoryEntity {user_id:$user}) WHERE NOT EXISTS { MATCH (:MemoryFact)-[:MENTIONS]->(n) } "
        "DETACH DELETE n",
        user=user_id,
    )
    await result.consume()
