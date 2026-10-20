"""Real SQL/Neo4j memory provenance, fading, deletion and process restart smoke."""

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

from smoke_neo4j import configure_graph


async def recovered(workspace):
    configure_graph(workspace)
    import httpx
    from main import app
    from memory_system.graph_lifecycle import (
        cleanup_pending,
        eligible_memory_ids,
        write_extracted_graph,
    )
    from memory_system.graph_store import graph_store
    from memory_system.lifecycle import capture_memory_epoch
    from shared_runtime.database import AsyncSessionLocal

    state = json.loads((workspace / "state.json").read_text())
    alice, bob, old, new, foreign = (
        state[key] for key in ("alice", "bob", "old", "new", "foreign")
    )
    async with app.router.lifespan_context(app):
        assert not await cleanup_pending(alice)
        assert await graph_store.get_memory_facts(alice, [old]) == []
        assert "current-coffee" in str(await graph_store.get_memory_facts(alice, [new]))
        assert "bob-tea" in str(await graph_store.get_memory_facts(bob, [foreign]))
        async with AsyncSessionLocal() as sql:
            assert await eligible_memory_ids(sql, alice, [old, new, foreign]) == {new}
        assert not await write_extracted_graph(
            alice,
            state["epoch"],
            {"preferences": [{"key": "drink", "value": "old-tea"}]},
            memory_id=old,
        )
        assert await graph_store.get_memory_facts(alice, [old]) == []
        try:
            await graph_store.store_memory_graph(
                alice,
                old,
                {"preferences": [{"key": "drink", "value": "late-old-tea"}]},
                expected_epoch=state["epoch"],
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "A delayed server-side write must respect the source tombstone"
            )
        entities = await graph_store.query(
            "MATCH (e:MemoryEntity {user_id:$user}) RETURN e.label AS label",
            {"user": alice},
        )
        assert {item["label"] for item in entities} == {"campus", "drink"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            headers = {"Authorization": "Bearer " + state["keys"][alice]}
            cleared = await client.delete(f"/memory/user/{alice}/all", headers=headers)
            assert (
                cleared.status_code == 200
                and cleared.json()["external_graph"] == "completed"
            )
            epoch = await capture_memory_epoch(alice)
            fresh = await client.post(
                "/memory/store",
                headers=headers,
                json={
                    "user_id": alice,
                    "content": "Fresh generation coffee",
                    "embedding": [0.1] * 1024,
                },
            )
            assert fresh.status_code == 200
            fresh_id = fresh.json()["entry_id"]
            assert await write_extracted_graph(
                alice,
                epoch,
                {"preferences": [{"key": "drink", "value": "fresh-generation"}]},
                memory_id=fresh_id,
            )
            try:
                await graph_store.store_memory_graph(
                    alice,
                    str(uuid4()),
                    {"preferences": [{"key": "drink", "value": "stale-generation"}]},
                    expected_epoch=state["epoch"],
                )
            except ValueError:
                pass
            else:
                raise AssertionError(
                    "A cleared generation must be fenced at the graph server"
                )
            await graph_store.delete_user_data(alice, epoch=epoch)
            assert "fresh-generation" in str(
                await graph_store.get_memory_facts(alice, [fresh_id])
            )
            assert "bob-tea" in str(await graph_store.get_memory_facts(bob, [foreign]))
            for user in (alice, bob):
                result = await client.post(
                    f"/privacy/user/{user}/erase",
                    headers={"Authorization": "Bearer " + state["keys"][user]},
                    json={"confirmation": "删除我的全部数据"},
                )
                assert result.status_code == 200, result.text
    print(
        "Actual restarted host removed only the deleted memory's graph; queued write refused; other sources preserved"
    )


async def main():
    if os.environ.get("COMPANION_TEST_NEO4J_ISOLATED") != "true":
        raise SystemExit("An explicitly isolated graph is required")
    workspace = Path(tempfile.mkdtemp(prefix="companion-evidence-smoke-"))
    configure_graph(workspace)
    alice, bob = "evidence-qa-" + uuid4().hex, "evidence-qa-" + uuid4().hex
    keys = {user: secrets.token_urlsafe(32) for user in (alice, bob)}
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
        )
    )
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, patch

    import httpx
    from main import app
    from memory_system.graph_lifecycle import cleanup_pending, write_extracted_graph
    from memory_system.graph_store import graph_store
    from memory_system.lifecycle import (
        MemoryStateORM,
        capture_memory_epoch,
        restore_memory,
    )
    from memory_system.recall import recall_memory
    from shared_runtime.database import AsyncSessionLocal
    from sqlalchemy import update

    state = {"alice": alice, "bob": bob, "keys": keys}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client,
    ):
        headers = {"Authorization": "Bearer " + keys[alice]}
        extracted_by_source = {}
        for name, user, value in [
            ("old", alice, "old-tea"),
            ("new", alice, "current-coffee"),
            ("foreign", bob, "bob-tea"),
        ]:
            response = await client.post(
                "/memory/store",
                headers={"Authorization": "Bearer " + keys[user]},
                json={
                    "user_id": user,
                    "content": "Synthetic campus drink " + value,
                    "embedding": [1.0] + [0.0] * 1023,
                },
            )
            assert response.status_code == 200, response.text
            memory = response.json()["entry_id"]
            state[name] = memory
            extracted = {
                "entities": [
                    {
                        "name": "campus",
                        "type": "place",
                        "properties": {"private": value},
                    }
                ],
                "preferences": [{"key": "drink", "value": value}],
            }
            extracted_by_source[name] = extracted
            assert await write_extracted_graph(
                user, await capture_memory_epoch(user), extracted, memory_id=memory
            )
        old, foreign = state["old"], state["foreign"]
        old_facts = await graph_store.get_user_facts(alice, memory_ids=[old])
        assert "old-tea" in str(old_facts) and "current-coffee" not in str(old_facts)
        assert await graph_store.get_user_facts(alice, memory_ids=[foreign]) == []
        try:
            await graph_store.store_memory_graph(
                alice,
                old,
                {"preferences": [{"key": "drink", "value": "wrong-overwrite"}]},
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "A memory projection must not change its immutable source"
            )
        assert await graph_store.get_user_facts(alice, memory_ids=[old]) == old_facts
        await graph_store.merge_user(alice)
        await graph_store.merge_entity(
            alice, "legacy-unattributed", properties={"private": "must-not-enter-reply"}
        )
        async with AsyncSessionLocal() as sql:
            await sql.execute(
                update(MemoryStateORM)
                .where(MemoryStateORM.memory_id == old)
                .values(dormant_since=datetime.now(UTC))
            )
            await sql.commit()
        # Only the embedding provider is a fixed offline fixture. Both actual
        # SQL and graph queries run through the normal recall implementation.
        with patch(
            "memory_system.vector_store._get_embedding",
            AsyncMock(return_value=[0.0, 1.0] + [0.0] * 1022),
        ):
            async with AsyncSessionLocal() as sql:
                faded = await recall_memory(sql, alice, "campus", top_k=10)
            assert "current-coffee" in str(faded.graph_facts) and "old-tea" not in str(
                faded.graph_facts
            )
            assert "must-not-enter-reply" not in str(
                faded.graph_facts
            ) and "bob-tea" not in str(faded.graph_facts)
            async with AsyncSessionLocal() as sql:
                assert await restore_memory(sql, alice, old)
            async with AsyncSessionLocal() as sql:
                restored = await recall_memory(sql, alice, "campus", top_k=10)
            assert "old-tea" in str(restored.graph_facts)
        state["epoch"] = await capture_memory_epoch(alice)
        transient = await client.post(
            "/memory/store",
            headers=headers,
            json={
                "user_id": alice,
                "content": "Temporary cleanup worker source",
                "embedding": [0.1] * 1024,
            },
        )
        assert transient.status_code == 200
        transient_id = transient.json()["entry_id"]
        assert await write_extracted_graph(
            alice,
            state["epoch"],
            {"preferences": [{"key": "temporary", "value": "worker-cleanup"}]},
            memory_id=transient_id,
        )
        await graph_store.close()
        assert (
            await client.delete(f"/memory/{transient_id}", headers=headers)
        ).status_code == 200
        assert await cleanup_pending(alice)
        await graph_store.connect()
        async with asyncio.timeout(12):
            while await cleanup_pending(alice):
                await asyncio.sleep(0.1)
        assert await graph_store.get_memory_facts(alice, [transient_id]) == []
        assert "current-coffee" in str(
            await graph_store.get_memory_facts(alice, [state["new"]])
        )
        await graph_store.close()
        removed = await client.delete(f"/memory/{old}", headers=headers)
        assert removed.status_code == 200
        assert await cleanup_pending(alice)
        summary = await client.get(f"/memory/user/{alice}/summary", headers=headers)
        assert summary.json()["external_graph_cleanup_pending"]
        (workspace / "state.json").write_text(json.dumps(state))
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--recover", str(workspace)],
        check=True,
    )
    print(
        "Actual provenance smoke passed: conflicting values stay independent, foreign/legacy/faded facts excluded, "
        "explicit restore, durable single-delete restart and late-write barrier"
    )


if __name__ == "__main__":
    asyncio.run(
        recovered(Path(sys.argv[2]))
        if len(sys.argv) > 1 and sys.argv[1] == "--recover"
        else main()
    )
