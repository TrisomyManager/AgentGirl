"""Neo4j knowledge graph wrapper for user entities, relationships, and events."""

import hashlib
import json
import re
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase

from shared_runtime.config import get_settings
from shared_runtime.log_safety import connection_target

logger = structlog.get_logger(__name__)

settings = get_settings()


def _identity(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


class GraphStore:
    """Async Neo4j graph store for companion knowledge graph."""

    def __init__(self) -> None:
        self._driver = None

    async def connect(self) -> None:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        try:
            await driver.verify_connectivity()
        except BaseException:
            await driver.close()
            raise
        self._driver = driver
        logger.info("graph_store.connected", target=connection_target(settings.neo4j_uri))

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("graph_store.closed")

    async def init_schema(self) -> None:
        """Create constraints and indexes for the knowledge graph."""
        async with self._driver.session() as session:
            # Unique constraints
            constraints = [
                "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
                "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE",
                "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (ev:Event) REQUIRE ev.event_id IS UNIQUE",
                "CREATE CONSTRAINT preference_id IF NOT EXISTS FOR (p:Preference) REQUIRE p.preference_id IS UNIQUE",
                "CREATE CONSTRAINT emotion_id IF NOT EXISTS FOR (em:Emotion) REQUIRE em.emotion_id IS UNIQUE",
                "CREATE CONSTRAINT memory_evidence_id IF NOT EXISTS "
                "FOR (n:MemoryEvidence) REQUIRE n.evidence_id IS UNIQUE",
                "CREATE CONSTRAINT memory_fact_id IF NOT EXISTS FOR (n:MemoryFact) REQUIRE n.fact_id IS UNIQUE",
                "CREATE CONSTRAINT memory_entity_id IF NOT EXISTS FOR (n:MemoryEntity) REQUIRE n.entity_id IS UNIQUE",
                "CREATE CONSTRAINT graph_owner_fence IF NOT EXISTS FOR (n:GraphFence) REQUIRE n.owner_key IS UNIQUE",
            ]
            for cypher in constraints:
                await session.run(cypher)
            # Indexes
            indexes = [
                "CREATE INDEX entity_name_idx IF NOT EXISTS FOR (e:Entity) ON (e.name)",
                "CREATE INDEX event_time_idx IF NOT EXISTS FOR (ev:Event) ON (ev.timestamp)",
                "CREATE INDEX preference_key_idx IF NOT EXISTS FOR (p:Preference) ON (p.key)",
                "CREATE INDEX memory_evidence_owner IF NOT EXISTS FOR (n:MemoryEvidence) ON (n.user_id,n.memory_id)",
                "CREATE INDEX memory_fact_owner IF NOT EXISTS FOR (n:MemoryFact) ON (n.user_id,n.memory_id)",
            ]
            for cypher in indexes:
                await session.run(cypher)
        logger.info("graph_store.schema_initialized")

    async def merge_user(self, user_id: str, profile: dict[str, Any] | None = None) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (u:User {user_id: $user_id})
                ON CREATE SET u.created_at = datetime(), u.profile_json = $profile
                ON MATCH SET u.updated_at = datetime(), u.profile_json = coalesce($profile, u.profile_json)
                """,
                user_id=user_id,
                profile=_json(profile),
            )

    async def merge_entity(
        self,
        user_id: str,
        entity_name: str,
        entity_type: str = "generic",
        properties: dict[str, Any] | None = None,
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (u:User {user_id: $user_id})
                MERGE (e:Entity {entity_id: $entity_id})
                ON CREATE SET e.user_id = $user_id, e.name = $entity_name, e.type = $entity_type,
                              e.created_at = datetime(), e.properties_json = $properties
                ON MATCH SET e.updated_at = datetime(), e.properties_json = coalesce($properties, e.properties_json)
                MERGE (u)-[:KNOWS]->(e)
                """,
                user_id=user_id,
                entity_name=entity_name,
                entity_type=entity_type,
                entity_id=_identity(user_id, entity_name, entity_type),
                properties=_json(properties),
            )

    async def merge_relationship(
        self,
        user_id: str,
        source_name: str,
        target_name: str,
        rel_type: str = "RELATED_TO",
        properties: dict[str, Any] | None = None,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", rel_type):
            raise ValueError("Invalid graph relationship type")
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (u:User {user_id: $user_id})
                MATCH (e1:Entity {user_id: $user_id, name: $source_name})
                MATCH (e2:Entity {user_id: $user_id, name: $target_name})
                MERGE (e1)-[r:__RELATION_TYPE__]->(e2)
                ON CREATE SET r.user_id = $user_id, r.created_at = datetime(), r.properties_json = $properties
                ON MATCH SET r.updated_at = datetime(), r.properties_json = coalesce($properties, r.properties_json)
                MERGE (u)-[:KNOWS]->(e1)
                MERGE (u)-[:KNOWS]->(e2)
                """.replace("__RELATION_TYPE__", rel_type),
                user_id=user_id,
                source_name=source_name,
                target_name=target_name,
                properties=_json(properties),
            )

    async def log_event(
        self,
        user_id: str,
        event_name: str,
        event_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (u:User {user_id: $user_id})
                MERGE (ev:Event {event_id: coalesce($event_id, randomUUID())})
                ON CREATE SET ev.user_id = $user_id, ev.name = $event_name,
                              ev.timestamp = datetime(), ev.properties_json = $properties
                ON MATCH SET ev.updated_at = datetime(), ev.properties_json = coalesce($properties, ev.properties_json)
                MERGE (u)-[:EXPERIENCED]->(ev)
                """,
                user_id=user_id,
                event_id=_identity(user_id, event_id) if event_id else None,
                event_name=event_name,
                properties=_json(properties),
            )

    async def add_preference(
        self,
        user_id: str,
        key: str,
        value: Any,
        strength: float = 0.5,
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (u:User {user_id: $user_id})
                MERGE (p:Preference {preference_id: $preference_id})
                ON CREATE SET p.user_id = $user_id, p.key = $key,
                              p.created_at = datetime(), p.value_json = $value, p.strength = $strength
                ON MATCH SET p.updated_at = datetime(), p.value_json = $value, p.strength = $strength
                MERGE (u)-[r:PREFERS]->(p)
                ON CREATE SET r.since = datetime()
                """,
                user_id=user_id,
                key=key,
                value=_json(value),
                preference_id=_identity(user_id, key),
                strength=strength,
            )

    async def add_emotion(
        self,
        user_id: str,
        emotion_tag: str,
        intensity: float = 0.5,
        trigger: str | None = None,
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (u:User {user_id: $user_id})
                CREATE (em:Emotion {user_id: $user_id, emotion_id: randomUUID(), tag: $emotion_tag,
                                    intensity: $intensity, trigger: $trigger, timestamp: datetime()})
                MERGE (u)-[:FELT]->(em)
                """,
                user_id=user_id,
                emotion_tag=emotion_tag,
                intensity=intensity,
                trigger=trigger,
            )

    async def get_neighborhood(
        self,
        user_id: str,
        depth: int = 2,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get the knowledge graph neighborhood for a user."""
        if isinstance(depth, bool) or depth not in (1, 2):
            raise ValueError("Graph depth must be 1 or 2")
        second_hop = (
            "OPTIONAL MATCH (n)-[r2]-(m) WHERE m <> u AND m.user_id = $user_id "
            if depth == 2 else "WITH u, r, n, null AS r2, null AS m "
        )
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (u:User {user_id: $user_id})-[r]-(n) WHERE n.user_id = $user_id "
                + second_hop + "RETURN u, r, n, r2, m LIMIT $limit",
                user_id=user_id,
                limit=limit,
            )
            records = []
            async for record in result:
                records.append(
                    {
                        "user": dict(record["u"]),
                        "rel": dict(record["r"]) if record["r"] else None,
                        "node": dict(record["n"]),
                        "rel2": dict(record["r2"]) if record["r2"] else None,
                        "node2": dict(record["m"]) if record["m"] else None,
                    }
                )
            return records

    async def query(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Run a raw Cypher query and return results."""
        async with self._driver.session() as session:
            result = await session.run(cypher, parameters or {})
            records = []
            async for record in result:
                records.append(dict(record))
            return records

    async def delete_user_data(self, user_id: str, *, epoch=None):
        """Remove owned nodes; ambiguous legacy shared nodes need explicit migration."""
        if self._driver is None:
            raise RuntimeError("Graph storage is unavailable")

        async def erase(transaction):
            from memory_system.graph_evidence import identity

            result = await transaction.run(
                "MERGE (g:GraphFence {owner_key:$key}) ON CREATE SET g.epoch=0 "
                "SET g._write_lock=true REMOVE g._write_lock "
                "RETURN g.epoch AS epoch,g.cleared_epoch AS cleared",
                key=identity(user_id),
            )
            fence = await result.single()
            target = epoch if epoch is not None else fence["epoch"] + 1
            if target < fence["epoch"] or fence["cleared"] == target:
                return  # A repeated old clear must not remove fresh-generation data.
            result = await transaction.run(
                "MATCH (u:User {user_id: $user_id})-->(n) "
                "WHERE n.user_id IS NULL AND EXISTS { MATCH (other:User)-->(n) "
                "WHERE other.user_id <> $user_id } RETURN count(n) AS ambiguous",
                user_id=user_id,
            )
            record = await result.single()
            if record and record["ambiguous"]:
                raise RuntimeError("Legacy shared graph ownership requires migration before erasure")
            await transaction.run(
                "MATCH (u:User {user_id: $user_id})-->(n) "
                "WHERE n.user_id IS NULL AND NOT n:User DETACH DELETE n", user_id=user_id,
            )
            await transaction.run("MATCH (n {user_id: $user_id}) DETACH DELETE n", user_id=user_id)
            result = await transaction.run(
                "MATCH (g:GraphFence {owner_key:$key}) SET g.epoch=$epoch,g.cleared_epoch=$epoch",
                key=identity(user_id), epoch=target,
            )
            await result.consume()

        async with self._driver.session() as session:
            await session.execute_write(erase)

    async def store_memory_graph(self, user_id, memory_id, extracted, *, expected_epoch=0):
        from memory_system.graph_evidence import project_facts, store

        facts = project_facts(user_id, memory_id, extracted)
        async with self._driver.session() as session:
            await session.execute_write(store, user_id, memory_id, facts, expected_epoch)

    async def delete_memory_graph(self, user_id, memory_id):
        await self.delete_memory_graphs(user_id, [memory_id])

    async def delete_memory_graphs(self, user_id, memory_ids):
        from memory_system.graph_evidence import delete

        if self._driver is None:
            raise RuntimeError("Graph storage is unavailable")
        async with self._driver.session() as session:
            await session.execute_write(delete, user_id, memory_ids)

    async def get_memory_facts(self, user_id, memory_ids=None, limit=20):
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (:User {user_id:$user})-[:HAS_MEMORY]->(e:MemoryEvidence)-[:SUPPORTS]->(f:MemoryFact) "
                "WHERE e.user_id=$user AND f.user_id=$user AND f.memory_id=e.memory_id "
                "AND coalesce(e.deleted,false)=false AND e.schema_version=1 "
                "AND ($ids IS NULL OR e.memory_id IN $ids) "
                "RETURN f.memory_id AS memory_id,f.text AS text ORDER BY f.fact_id LIMIT $limit",
                user=user_id, ids=memory_ids, limit=max(0, min(1000, limit)),
            )
            return await result.data()

    async def get_user_facts(self, user_id: str, limit: int = 20, *, memory_ids=None) -> list[str]:
        """Extract readable facts about a user from the graph."""
        derived = [item["text"] for item in await self.get_memory_facts(user_id, memory_ids, limit)]
        if memory_ids is not None:
            return derived
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (u:User {user_id: $user_id})-[:KNOWS]->(e:Entity)
                WHERE e.user_id = $user_id
                RETURN e.name AS name, e.type AS type, e.properties_json AS props
                LIMIT $limit
                """,
                user_id=user_id,
                limit=limit,
            )
            facts = []
            async for record in result:
                name = record["name"]
                etype = record["type"]
                props = json.loads(record["props"] or "{}")
                prop_str = ", ".join(f"{k}={v}" for k, v in props.items())
                fact = f"User knows {etype}: {name}" + (f" ({prop_str})" if prop_str else "")
                facts.append(fact)

            # Preferences
            pref_result = await session.run(
                """
                MATCH (u:User {user_id: $user_id})-[:PREFERS]->(p:Preference)
                WHERE p.user_id = $user_id
                RETURN p.key AS key, p.value_json AS value, p.strength AS strength
                LIMIT $limit
                """,
                user_id=user_id,
                limit=limit,
            )
            async for record in pref_result:
                facts.append(
                    f"User prefers {record['key']} = {record['value']} (strength: {record['strength']:.2f})"
                )

            # Events
            event_result = await session.run(
                """
                MATCH (u:User {user_id: $user_id})-[:EXPERIENCED]->(ev:Event)
                WHERE ev.user_id = $user_id
                RETURN ev.name AS name, ev.timestamp AS ts
                ORDER BY ev.timestamp DESC
                LIMIT $limit
                """,
                user_id=user_id,
                limit=limit,
            )
            async for record in event_result:
                facts.append(f"User experienced: {record['name']} at {record['ts']}")

            return (derived + facts)[:limit]


graph_store = GraphStore()
