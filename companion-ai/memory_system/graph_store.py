"""Neo4j knowledge graph wrapper for user entities, relationships, and events."""

from typing import Any, Dict, List, Optional

import structlog
from neo4j import AsyncGraphDatabase

from shared.config import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()


class GraphStore:
    """Async Neo4j graph store for companion knowledge graph."""

    def __init__(self) -> None:
        self._driver = None

    async def connect(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        await self._driver.verify_connectivity()
        logger.info("graph_store.connected", uri=settings.neo4j_uri)

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
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
            ]
            for cypher in constraints:
                await session.run(cypher)
            # Indexes
            indexes = [
                "CREATE INDEX entity_name_idx IF NOT EXISTS FOR (e:Entity) ON (e.name)",
                "CREATE INDEX event_time_idx IF NOT EXISTS FOR (ev:Event) ON (ev.timestamp)",
                "CREATE INDEX preference_key_idx IF NOT EXISTS FOR (p:Preference) ON (p.key)",
            ]
            for cypher in indexes:
                await session.run(cypher)
        logger.info("graph_store.schema_initialized")

    async def merge_user(self, user_id: str, profile: Optional[Dict[str, Any]] = None) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (u:User {user_id: $user_id})
                ON CREATE SET u.created_at = datetime(), u.profile = $profile
                ON MATCH SET u.updated_at = datetime(), u.profile = coalesce($profile, u.profile)
                """,
                user_id=user_id,
                profile=profile or {},
            )

    async def merge_entity(
        self,
        user_id: str,
        entity_name: str,
        entity_type: str = "generic",
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (u:User {user_id: $user_id})
                MERGE (e:Entity {name: $entity_name, type: $entity_type})
                ON CREATE SET e.created_at = datetime(), e.properties = $properties
                ON MATCH SET e.updated_at = datetime(), e.properties = coalesce($properties, e.properties)
                MERGE (u)-[:KNOWS]->(e)
                """,
                user_id=user_id,
                entity_name=entity_name,
                entity_type=entity_type,
                properties=properties or {},
            )

    async def merge_relationship(
        self,
        user_id: str,
        source_name: str,
        target_name: str,
        rel_type: str = "RELATED_TO",
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (u:User {user_id: $user_id})
                MATCH (e1:Entity {name: $source_name})
                MATCH (e2:Entity {name: $target_name})
                MERGE (e1)-[r:%s]->(e2)
                ON CREATE SET r.created_at = datetime(), r.properties = $properties
                ON MATCH SET r.updated_at = datetime(), r.properties = coalesce($properties, r.properties)
                MERGE (u)-[:KNOWS]->(e1)
                MERGE (u)-[:KNOWS]->(e2)
                """
                % rel_type,
                user_id=user_id,
                source_name=source_name,
                target_name=target_name,
                properties=properties or {},
            )

    async def log_event(
        self,
        user_id: str,
        event_name: str,
        event_id: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (u:User {user_id: $user_id})
                MERGE (ev:Event {event_id: coalesce($event_id, randomUUID())})
                ON CREATE SET ev.name = $event_name, ev.timestamp = datetime(), ev.properties = $properties
                ON MATCH SET ev.updated_at = datetime(), ev.properties = coalesce($properties, ev.properties)
                MERGE (u)-[:EXPERIENCED]->(ev)
                """,
                user_id=user_id,
                event_id=event_id,
                event_name=event_name,
                properties=properties or {},
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
                MERGE (p:Preference {key: $key})
                ON CREATE SET p.created_at = datetime(), p.value = $value, p.strength = $strength
                ON MATCH SET p.updated_at = datetime(), p.value = $value, p.strength = $strength
                MERGE (u)-[r:PREFERS]->(p)
                ON CREATE SET r.since = datetime()
                """,
                user_id=user_id,
                key=key,
                value=value,
                strength=strength,
            )

    async def add_emotion(
        self,
        user_id: str,
        emotion_tag: str,
        intensity: float = 0.5,
        trigger: Optional[str] = None,
    ) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (u:User {user_id: $user_id})
                CREATE (em:Emotion {emotion_id: randomUUID(), tag: $emotion_tag, intensity: $intensity, trigger: $trigger, timestamp: datetime()})
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
    ) -> List[Dict[str, Any]]:
        """Get the knowledge graph neighborhood for a user."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (u:User {user_id: $user_id})-[r]-(n)
                OPTIONAL MATCH (n)-[r2]-(m)
                WHERE m <> u
                RETURN u, r, n, r2, m
                LIMIT $limit
                """,
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

    async def query(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Run a raw Cypher query and return results."""
        async with self._driver.session() as session:
            result = await session.run(cypher, parameters or {})
            records = []
            async for record in result:
                records.append({key: record[key] for key in record.keys()})
            return records

    async def get_user_facts(self, user_id: str, limit: int = 20) -> List[str]:
        """Extract readable facts about a user from the graph."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (u:User {user_id: $user_id})-[:KNOWS]->(e:Entity)
                RETURN e.name AS name, e.type AS type, e.properties AS props
                LIMIT $limit
                """,
                user_id=user_id,
                limit=limit,
            )
            facts = []
            async for record in result:
                name = record["name"]
                etype = record["type"]
                props = record["props"] or {}
                prop_str = ", ".join(f"{k}={v}" for k, v in props.items())
                fact = f"User knows {etype}: {name}" + (f" ({prop_str})" if prop_str else "")
                facts.append(fact)

            # Preferences
            pref_result = await session.run(
                """
                MATCH (u:User {user_id: $user_id})-[:PREFERS]->(p:Preference)
                RETURN p.key AS key, p.value AS value, p.strength AS strength
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
                RETURN ev.name AS name, ev.timestamp AS ts
                ORDER BY ev.timestamp DESC
                LIMIT $limit
                """,
                user_id=user_id,
                limit=limit,
            )
            async for record in event_result:
                facts.append(f"User experienced: {record['name']} at {record['ts']}")

            return facts


graph_store = GraphStore()
