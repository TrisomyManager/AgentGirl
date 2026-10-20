"""Reviewed, atomic migration from shared legacy graph nodes to owned nodes.

Run with writers stopped. Dry-run never changes graph data. Shared properties
and relationships require explicit per-user review, rather than guessing who
supplied an old merged value. A private archive is mandatory before applying.
"""

import hashlib
import json
import re
from pathlib import Path

LABELS = {"Entity": "entity_id", "Event": "event_id", "Preference": "preference_id", "Emotion": "emotion_id"}


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=lambda item: {"neo4j_type": type(item).__name__, "value": str(item)},
    )


def fingerprint(snapshot):
    return hashlib.sha256(_json(snapshot).encode()).hexdigest()


async def snapshot(transaction, limit=1000):
    result = await transaction.run(
        "MATCH (n) WHERE n.user_id IS NULL AND any(label IN labels(n) WHERE label IN $labels) "
        "RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props ORDER BY id LIMIT $limit",
        labels=list(LABELS),
        limit=limit + 1,
    )
    candidates = await result.data()
    if len(candidates) > limit:
        raise RuntimeError("Migration exceeds node limit; use an offline partition plan")
    if not candidates:
        return {"nodes": [], "edges": [], "endpoints": []}
    ids = [item["id"] for item in candidates]
    result = await transaction.run(
        "MATCH (a)-[r]->(b) WHERE elementId(a) IN $ids OR elementId(b) IN $ids "
        "RETURN elementId(r) AS id, elementId(a) AS source, elementId(b) AS target, "
        "type(r) AS type, properties(r) AS props ORDER BY id LIMIT 10001",
        ids=ids,
    )
    edges = await result.data()
    if len(edges) > 10000:
        raise RuntimeError("Migration exceeds relationship limit")
    endpoint_ids = sorted({item[key] for item in edges for key in ("source", "target")})
    result = await transaction.run(
        "MATCH (n) WHERE elementId(n) IN $ids RETURN elementId(n) AS id, "
        "labels(n) AS labels, properties(n) AS props ORDER BY id",
        ids=endpoint_ids,
    )
    endpoints = await result.data()
    state = {"nodes": candidates, "edges": edges, "endpoints": endpoints}
    if len(_json(state).encode()) > 10 * 1024 * 1024:
        raise RuntimeError("Migration archive exceeds ten MiB")
    return state


def review_template(state):
    owners = {}
    nodes = {item["id"]: item for item in state["endpoints"]}
    for candidate in state["nodes"]:
        known = set()
        for edge in state["edges"]:
            if edge["target"] != candidate["id"]:
                continue
            source = nodes[edge["source"]]
            if "User" in source["labels"] and source["props"].get("user_id"):
                known.add(source["props"]["user_id"])
        owners[candidate["id"]] = sorted(known)
    return {
        "format": "companion.graph-migration.v1",
        "fingerprint": fingerprint(state),
        "nodes": {item["id"]: {"owners": owners[item["id"]], "properties_by_user": {}} for item in state["nodes"]},
        "edges": {},
    }


def plan(state, review):
    template = review_template(state)
    if review.get("format") != template["format"] or review.get("fingerprint") != template["fingerprint"]:
        raise ValueError("Review is stale or has an unsupported format")
    endpoints = {item["id"]: item for item in state["endpoints"]}
    projected, unresolved, occupied = {}, [], set()
    for node in state["nodes"]:
        node_id = node["id"]
        item = review.get("nodes", {}).get(node_id, {})
        known = template["nodes"][node_id]["owners"]
        owners = item.get("owners", [])
        if sorted(owners) != known or not known:
            unresolved.append(node_id)
            continue
        kinds = set(node["labels"]) & set(LABELS)
        if len(kinds) != 1 or set(node["labels"]) != kinds:
            raise ValueError("Unsupported legacy node labels require manual migration")
        kind = kinds.pop()
        for owner in owners:
            original = dict(node["props"])
            if len(owners) > 1:
                supplied = item.get("properties_by_user", {}).get(owner)
                if not isinstance(supplied, dict) or not supplied:
                    unresolved.append(node_id + ":" + owner)
                    continue
                props = dict(supplied)
            else:
                props = original
            if kind == "Entity":
                if not isinstance(props.get("name"), str) or not props["name"]:
                    raise ValueError("Entity review requires a name")
                parts = [owner, props["name"], props.get("type", "generic")]
                props.setdefault("type", "generic")
            elif kind == "Preference":
                if not props.get("key"):
                    raise ValueError("Preference review requires a key")
                parts = [owner, props["key"]]
            else:
                parts = [owner, original.get(LABELS[kind]) or node_id]
            identifier = hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()
            identity = (kind, identifier)
            if identity in occupied:
                raise ValueError("Multiple old nodes resolve to one identity; reconcile before migration")
            occupied.add(identity)
            props.update(user_id=owner, **{LABELS[kind]: identifier})
            props.pop("_companion_migration_lock", None)
            projected[(node_id, owner)] = {"kind": kind, "identifier": identifier, "props": props}
    edges = []
    for edge in state["edges"]:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", edge["type"]):
            raise ValueError("Unsupported legacy relationship name")
        sets = []
        for node_id in (edge["source"], edge["target"]):
            if node_id in template["nodes"]:
                sets.append(set(template["nodes"][node_id]["owners"]))
            else:
                owner = endpoints[node_id]["props"].get("user_id")
                sets.append({owner} if owner else set())
        possible = sets[0] & sets[1]
        declared = edge["props"].get("user_id")
        if declared:
            possible &= {declared}
        if len(possible) == 1:
            values = {next(iter(possible)): edge["props"]}
        else:
            values = review.get("edges", {}).get(edge["id"], {}).get("properties_by_user")
            if not isinstance(values, dict) or not set(values) <= possible or not values:
                unresolved.append(edge["id"])
                continue
        for owner, props in values.items():
            if not isinstance(props, dict):
                raise ValueError("Relationship properties must be explicitly reviewed per user")
            edges.append({**edge, "owner": owner, "props": dict(props, user_id=owner)})
    return projected, edges, sorted(set(unresolved))


def write_private(path: Path, payload):
    # Exclusive creation and no symlink following; never overwrite an archive.
    import os

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(_json(payload))
        output.flush()
        os.fsync(output.fileno())


async def apply(transaction, expected, review):
    ids = {item["id"] for item in expected["nodes"] + expected["endpoints"]}
    if any("_companion_migration_lock" in item["props"] for item in expected["nodes"] + expected["endpoints"]):
        raise ValueError("Reserved migration property already exists")
    result = await transaction.run(
        "MATCH (n) WHERE elementId(n) IN $ids SET n._companion_migration_lock=true "
        "REMOVE n._companion_migration_lock RETURN count(n) AS locked",
        ids=list(ids),
    )
    await result.consume()
    actual = await snapshot(transaction)
    if fingerprint(actual) != fingerprint(expected):
        raise ValueError("Graph changed after review; export a fresh review")
    projected, edges, unresolved = plan(actual, review)
    if unresolved:
        raise ValueError("Shared or orphan data still requires explicit ownership review")
    targets = {}
    for (source, owner), node in projected.items():
        kind, field = node["kind"], LABELS[node["kind"]]
        result = await transaction.run(
            f"MATCH (n:{kind} {{{field}: $id}}) RETURN elementId(n) AS id", id=node["identifier"]
        )
        if await result.single():
            raise ValueError("An owned target already exists; reconcile without overwriting current data")
        result = await transaction.run(
            f"CREATE (n:{kind}) SET n=$props RETURN elementId(n) AS id",
            props=node["props"],
        )
        targets[(source, owner)] = (await result.single())["id"]
    for edge in edges:
        owner = edge["owner"]
        source = targets.get((edge["source"], owner), edge["source"])
        target = targets.get((edge["target"], owner), edge["target"])
        result = await transaction.run(
            f"MATCH (a),(b) WHERE elementId(a)=$source AND elementId(b)=$target "
            f"CREATE (a)-[r:{edge['type']}]->(b) SET r=$props",
            source=source,
            target=target,
            props=edge["props"],
        )
        await result.consume()
    result = await transaction.run(
        "MATCH (n) WHERE elementId(n) IN $ids DETACH DELETE n", ids=[n["id"] for n in actual["nodes"]]
    )
    await result.consume()
    return {"migrated_nodes": len(actual["nodes"]), "owned_nodes": len(projected), "owned_edges": len(edges)}


def cli():
    import argparse
    import asyncio

    from neo4j import AsyncGraphDatabase

    from shared_runtime.config import get_settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-review", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if args.apply and (not args.review or not args.backup):
        parser.error("--apply requires a reviewed --review file and a new private --backup path")

    async def execute():
        settings = get_settings()
        async with AsyncGraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        ) as driver, driver.session() as session:
            state = await session.execute_read(snapshot)
            review = json.loads(args.review.read_text(encoding="utf-8")) if args.review else review_template(state)
            projected, edges, unresolved = plan(state, review)
            report = {
                "legacy_nodes": len(state["nodes"]),
                "owned_nodes": len(projected),
                "owned_edges": len(edges),
                "unresolved": len(unresolved),
            }
            if args.export_review:
                write_private(args.export_review, {**review, "source": state})
            if args.apply:
                if unresolved:
                    raise SystemExit("Ownership review is incomplete; graph data unchanged")
                write_private(args.backup, state)
                report.update(await session.execute_write(apply, state, review))
            print(json.dumps(report))

    asyncio.run(execute())


if __name__ == "__main__":
    cli()
