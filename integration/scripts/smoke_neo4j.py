"""Actual Neo4j owner isolation, reviewed migration, and host privacy smoke.

Requires an EMPTY dedicated test graph and COMPANION_TEST_NEO4J_ISOLATED=true.
All graph nodes created during the run are synthetic and removed afterward.
"""

import asyncio
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from smoke_postgres import configure


def configure_graph(workspace):
    configure(workspace)
    os.environ.update(
        COMPANION_ENABLE_KNOWLEDGE_GRAPH="true",
        COMPANION_NEO4J_URI=os.environ["COMPANION_TEST_NEO4J_URI"],
        COMPANION_NEO4J_PASSWORD=os.environ["COMPANION_TEST_NEO4J_PASSWORD"],
    )


async def recovery(workspace):
    configure_graph(workspace)
    from main import app
    from memory_system.graph_lifecycle import cleanup_pending
    from memory_system.graph_store import graph_store

    user = json.loads((workspace / "recovery.json").read_text())["user"]
    async with app.router.lifespan_context(app):
        assert not await cleanup_pending(user)
        assert await graph_store.get_user_facts(user) == []
    print("Actual restarted host completed durable memory graph cleanup")


async def main():
    if os.environ.get("COMPANION_TEST_NEO4J_ISOLATED") != "true":
        raise SystemExit("An explicitly isolated empty test graph is required")
    workspace = Path(tempfile.mkdtemp(prefix="companion-graph-smoke-"))
    configure_graph(workspace)
    users = ["graph-qa-" + uuid4().hex for _ in range(2)]
    alice, bob = users
    keys = {user: secrets.token_urlsafe(32) for user in users}
    (workspace / "access.json").write_text(
        json.dumps(
            {
                "access_keys": [
                    {
                        "user_id": user,
                        "role": "user",
                        "sha256": hashlib.sha256(key.encode()).hexdigest(),
                    }
                    for user, key in keys.items()
                ]
            }
        ),
        encoding="utf-8",
    )

    import httpx
    from sqlalchemy import select

    from main import app
    from memory_system.graph_migration import (
        apply,
        plan,
        review_template,
        snapshot,
        write_private,
    )
    from memory_system.graph_store import graph_store
    from shared_runtime.database import AsyncSessionLocal

    await graph_store.connect()
    count = (await graph_store.query("MATCH (n) WHERE NOT n:GraphFence RETURN count(n) AS count"))[0]["count"]
    if count:
        await graph_store.close()
        raise SystemExit("Test graph is not empty; no graph data was changed")
    try:
        await graph_store.init_schema()
        for user, value in [(alice, "alice-tea"), (bob, "bob-coffee")]:
            await graph_store.merge_user(user, {"name": user})
            await graph_store.merge_entity(
                user, "same-name", "hobby", {"private": value, "nested": {"count": 1}}
            )
            await graph_store.merge_entity(user, "next-entity", "place")
            await graph_store.merge_relationship(
                user, "same-name", "next-entity", "VISITED", {"private": value}
            )
            await graph_store.add_preference(user, "drink", value)
            await graph_store.log_event(
                user, "shared-event-id", "fixed-id", {"private": value}
            )
            await graph_store.add_emotion(user, "happy")
        a_facts = " ".join(await graph_store.get_user_facts(alice))
        assert "alice-tea" in a_facts and "bob-coffee" not in a_facts
        assert all(
            item["node2"] is None
            for item in await graph_store.get_neighborhood(alice, depth=1)
        )
        assert any(
            item["node2"] is not None
            for item in await graph_store.get_neighborhood(alice, depth=2)
        )
        try:
            await graph_store.merge_relationship(
                alice, "same-name", "next-entity", "BAD` QUERY"
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid relationship names must be rejected")

        await graph_store.query(
            "MATCH (a:User {user_id:$alice}),(b:User {user_id:$bob}) "
            "CREATE (e:Entity {entity_id:'old-shared-id',name:'legacy-school',type:'school',"
            'properties_json:\'{"private":"ambiguous-old-property"}\'}) '
            "CREATE (p:Preference {preference_id:'old-pref-id',key:'legacy-drink',"
            "value_json:'\"ambiguous-old-value\"'}) "
            "CREATE (v:Event {event_id:'old-event-id',name:'legacy-event',timestamp:datetime()}) "
            "CREATE (m:Emotion {emotion_id:'old-emotion-id',tag:'happy',timestamp:datetime()}) "
            "CREATE (a)-[:KNOWS]->(e),(b)-[:KNOWS]->(e),(a)-[:PREFERS]->(p),(b)-[:PREFERS]->(p),"
            '(e)-[:RELATED_TO {properties_json:\'{"private":"ambiguous-old-edge"}\'}]->(p),'
            "(a)-[:EXPERIENCED]->(v),(a)-[:FELT]->(m)",
            {"alice": alice, "bob": bob},
        )
        try:
            await graph_store.delete_user_data(alice)
        except RuntimeError:
            pass
        else:
            raise AssertionError(
                "Erasure must wait for ambiguous shared-node migration"
            )
        async with graph_store._driver.session() as session:
            state = await session.execute_read(snapshot)
            review = review_template(state)
            assert len(state["nodes"]) == 4 and plan(state, review)[2]
            write_private(workspace / "legacy-private-archive.json", state)
            try:
                await session.execute_write(apply, state, review)
            except ValueError:
                pass
            else:
                raise AssertionError("Shared properties must not be guessed")
            assert await session.execute_read(snapshot) == state
            for node in state["nodes"]:
                if "Entity" in node["labels"]:
                    review["nodes"][node["id"]]["properties_by_user"] = {
                        user: {
                            "name": "legacy-school",
                            "type": "school",
                            "properties_json": json.dumps({"private": value}),
                        }
                        for user, value in [
                            (alice, "alice-reviewed"),
                            (bob, "bob-reviewed"),
                        ]
                    }
                elif "Preference" in node["labels"]:
                    review["nodes"][node["id"]]["properties_by_user"] = {
                        user: {
                            "key": "legacy-drink",
                            "value_json": json.dumps(value),
                            "strength": 0.5,
                        }
                        for user, value in [
                            (alice, "alice-reviewed"),
                            (bob, "bob-reviewed"),
                        ]
                    }
            ambiguous_edge = next(
                edge for edge in state["edges"] if edge["type"] == "RELATED_TO"
            )
            review["edges"][ambiguous_edge["id"]] = {
                "properties_by_user": {
                    user: {"properties_json": json.dumps({"private": value})}
                    for user, value in [
                        (alice, "alice-reviewed"),
                        (bob, "bob-reviewed"),
                    ]
                }
            }
            assert not plan(state, review)[2]
            stale = dict(review, fingerprint="stale")
            try:
                await session.execute_write(apply, state, stale)
            except ValueError:
                pass
            else:
                raise AssertionError("A stale review must be refused")
            result = await session.execute_write(apply, state, review)
            assert result["migrated_nodes"] == 4 and result["owned_nodes"] == 6
            assert (await session.execute_read(snapshot))["nodes"] == []
        for user, owned, other in [
            (alice, "alice-reviewed", "bob-reviewed"),
            (bob, "bob-reviewed", "alice-reviewed"),
        ]:
            facts = " ".join(await graph_store.get_user_facts(user))
            assert (
                owned in facts and other not in facts and "ambiguous-old" not in facts
            )
        await graph_store.close()

        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
            ) as client,
        ):
            headers = {"Authorization": "Bearer " + keys[alice]}
            response = await client.post(
                "/memory/store",
                headers=headers,
                json={
                    "user_id": alice,
                    "content": "Synthetic graph/SQL erase fixture",
                    "embedding": [0.1] * 1024,
                },
            )
            assert response.status_code == 200
            exported = await client.get(
                f"/privacy/user/{alice}/export", headers=headers
            )
            assert (
                exported.status_code == 200
                and "alice-reviewed" in exported.text
                and "bob-reviewed" not in exported.text
            )
            # A real closed graph connection leaves a durable external-cleanup
            # receipt. Reconnection retries erasure without restoring SQL rows.
            await graph_store.close()
            erased = await client.post(
                f"/privacy/user/{alice}/erase",
                headers=headers,
                json={"confirmation": "删除我的全部数据"},
            )
            assert erased.status_code == 202 and "graph" in erased.json()["pending"], (
                erased.text
            )
            await graph_store.connect()
            retried = await client.post(
                f"/privacy/user/{alice}/erase",
                headers=headers,
                json={"confirmation": "删除我的全部数据"},
            )
            assert (
                retried.status_code == 200 and retried.json()["status"] == "completed"
            )
            assert await graph_store.get_user_facts(alice) == []
            assert "bob-reviewed" in " ".join(await graph_store.get_user_facts(bob))
            from core_orchestrator.privacy import ErasureJobORM

            async with AsyncSessionLocal() as sql:
                assert (
                    await sql.scalar(
                        select(ErasureJobORM.status).where(
                            ErasureJobORM.user_id == alice
                        )
                    )
                    == "completed"
                )
            bob_erase = await client.post(
                f"/privacy/user/{bob}/erase",
                headers={"Authorization": "Bearer " + keys[bob]},
                json={"confirmation": "删除我的全部数据"},
            )
            assert bob_erase.status_code == 200
            from memory_system.graph_lifecycle import write_extracted_graph
            from memory_system.lifecycle import capture_memory_epoch

            await graph_store.merge_user(alice)
            await graph_store.merge_entity(alice, "pending-clear-entity", "test")
            epoch = await capture_memory_epoch(alice)
            await graph_store.close()
            cleared = await client.delete(f"/memory/user/{alice}/all", headers=headers)
            assert cleared.status_code == 200 and cleared.json()["external_graph"] == "pending"
            summary = await client.get(f"/memory/user/{alice}/summary", headers=headers)
            assert summary.json()["external_graph_cleanup_pending"]
            hidden = await client.get(f"/privacy/user/{alice}/export", headers=headers)
            assert hidden.json()["external"]["graph"]["status"] == "pending_memory_clear"
            await graph_store.connect()
            assert not await write_extracted_graph(alice, epoch, {})
            assert not await write_extracted_graph(alice, await capture_memory_epoch(alice), {})
            (workspace / "recovery.json").write_text(json.dumps({"user": alice}))
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--recover", str(workspace)], check=True)
        print(
            "Actual Neo4j: nested properties, same-name/event owner isolation, one/two hops, reviewed migration, "
            "atomic refusal, private archive, host export and durable SQL/graph erasure retry passed"
        )
    finally:
        if graph_store._driver is None:
            await graph_store.connect()
        # The empty-graph precondition above establishes exclusive ownership of
        # this disposable test database; no existing application graph is used.
        await graph_store.query("MATCH (n) DETACH DELETE n")
        await graph_store.close()


if __name__ == "__main__":
    asyncio.run(recovery(Path(sys.argv[2])) if len(sys.argv) > 1 and sys.argv[1] == "--recover" else main())
