"""Exercise the actual reference host on an isolated PostgreSQL/pgvector database.

Set COMPANION_TEST_POSTGRES_URL and COMPANION_TEST_REDIS_URL. The database name
must identify a companion test/QA database. No production tables are truncated;
each run uses fresh synthetic users. Two child processes verify restart state.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/backend"))


def configure(workspace):
    from sqlalchemy.engine import make_url

    url = os.environ.get("COMPANION_TEST_POSTGRES_URL", "")
    parsed = make_url(url)
    name = parsed.database or ""
    if parsed.get_backend_name() != "postgresql" or not re.fullmatch(
        r"companion_(?:(?:qa|test)_[a-z0-9_]+|[a-z0-9_]+_(?:qa|test))", name
    ):
        raise SystemExit(
            "An explicitly isolated companion_*_qa/test database is required"
        )
    redis_url = os.environ.get("COMPANION_TEST_REDIS_URL")
    if not redis_url:
        raise SystemExit(
            "COMPANION_TEST_REDIS_URL is required; use a private test cache"
        )
    os.environ.update(
        COMPANION_LITE_MODE="false",
        COMPANION_MONOLITHIC="true",
        COMPANION_POSTGRES_URL=url,
        COMPANION_REDIS_URL=redis_url,
        COMPANION_ENABLE_KNOWLEDGE_GRAPH="false",
        COMPANION_ENABLE_VOICE="false",
        COMPANION_ENABLE_MEMORY_PIPELINE="false",
        COMPANION_PROACTIVE_ENABLED="false",
        COMPANION_MEMORY_MAINTENANCE_ENABLED="false",
        COMPANION_LOG_LEVEL="CRITICAL",
        COMPANION_REACTION_USE_LLM="false",
        COMPANION_INTENT_ROUTER_USE_LLM="false",
        COMPANION_WORKING_MEMORY_COMPRESSION_USE_LLM="false",
        COMPANION_ACCESS_CONFIG_FILE=str(workspace / "access.json"),
        COMPANION_LLM_CONFIG_PATH=str(workspace / "no-llm.json"),
        COMPANION_VOICE_CONFIG_PATH=str(workspace / "no-voice.json"),
        COMPANION_VOICE_TEMP_DIR=str(workspace / "voice"),
        COMPANION_PLUGINS_DIR=str(workspace / "plugins"),
        COMPANION_PLUGINS_CONFIG_FILE=str(workspace / "no-grants.json"),
        COMPANION_MCP_CONFIG_FILE=str(workspace / "no-mcp.json"),
    )


async def phase(name, workspace):
    configure(workspace)
    import logging
    from unittest.mock import AsyncMock, patch

    import httpx
    import structlog
    from sqlalchemy import func, select, text
    from sqlalchemy.exc import DBAPIError

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL)
    )
    from main import app
    from memory_system.lifecycle import StaleMemoryWriteError, capture_memory_epoch
    from memory_system.session_store import PersistentSessionMemory
    from memory_system.vector_store import (
        list_user_memories,
        search_similar,
        store_memory,
    )
    from persona_engine.emotion_engine import EmotionEngine
    from persona_engine.reaction_service import ReactionService
    from persona_engine.relationship_tracker import RelationshipTracker
    from persona_engine.state_store import PersonaEventORM, PersonaStateStore
    from shared_contracts import EmotionTag, MemoryEntry
    from shared_runtime.database import AsyncSessionLocal

    state = json.loads((workspace / "state.json").read_text())
    alice, bob = state["alice"], state["bob"]
    headers = {"Authorization": "Bearer " + state["keys"][alice]}
    embedding = [1.0] + [0.0] * 1023
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client,
    ):
        assert (await client.get("/health")).status_code == 200 and app.state.ready
        if name == "seed":
            for user in (alice, bob):
                result = await client.post(
                    "/memory/store",
                    headers={"Authorization": "Bearer " + state["keys"][user]},
                    json={
                        "user_id": user,
                        "content": user + " synthetic tea preference",
                        "embedding": embedding,
                        "emotion_tags": ["happy", "calm"],
                        "importance": 0.8,
                    },
                )
                assert result.status_code == 200, result.text
                state[user + "_memory"] = result.json()["entry_id"]
            history = PersistentSessionMemory()
            await history.authorize_session(state["session"], alice, claim=True)
            await history.add_turn(
                state["session"],
                "seed-turn",
                "Synthetic turn",
                "Synthetic reply",
                metadata={"user_id": alice},
            )
            await history.save_digest(
                state["session"], {"text": "Synthetic persisted digest"}
            )
            store = PersonaStateStore(AsyncSessionLocal)
            await store.initialize()
            service = ReactionService(
                EmotionEngine(state_store=store), RelationshipTracker(state_store=store)
            )
            await asyncio.gather(
                *[
                    service.commit(alice, f"sql-turn-{i % 6}", "谢谢你")
                    for i in range(18)
                ]
            )
            assert (await store.get_relationship(alice)).total_interactions == 6
            async with AsyncSessionLocal() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(PersonaEventORM)
                        .where(PersonaEventORM.user_id == alice)
                    )
                    == 6
                )
                with patch(
                    "memory_system.vector_store._get_embedding",
                    AsyncMock(return_value=embedding),
                ):
                    entries = await search_similar(
                        session, alice, "synthetic tea", top_k=5
                    )
                assert entries and entries[0].entry_id == state[alice + "_memory"]
                assert entries[0].emotion_tags == [EmotionTag.HAPPY, EmotionTag.CALM]
                assert all(item.user_id == alice for item in entries)
            try:
                async with AsyncSessionLocal() as session:
                    await store_memory(
                        session,
                        MemoryEntry(
                            entry_id="",
                            user_id=alice,
                            category="fact",
                            content="invalid dimensional write",
                            embedding=[1.0, 0.0],
                        ),
                    )
            except DBAPIError:
                pass
            else:
                raise AssertionError("pgvector must reject an incompatible vector")
            async with AsyncSessionLocal() as session:
                assert len(await list_user_memories(session, alice)) == 1
            (workspace / "state.json").write_text(json.dumps(state))
        else:
            assert (
                await client.get(f"/memory/user/{bob}/list", headers=headers)
            ).status_code == 403
            listed = await client.get(f"/memory/user/{alice}/list", headers=headers)
            assert (
                listed.status_code == 200
                and listed.json()[0]["entry_id"] == state[alice + "_memory"]
            )
            history = PersistentSessionMemory()
            assert (await history.get_session_turns(state["session"]))[0][
                "turn_id"
            ] == "seed-turn"
            assert (await history.load_digest(state["session"]))[
                "text"
            ] == "Synthetic persisted digest"
            try:
                await history.authorize_session(state["session"], bob)
            except PermissionError:
                pass
            else:
                raise AssertionError("Foreign session must be rejected")
            store = PersonaStateStore(AsyncSessionLocal)
            assert (await store.get_relationship(alice)).total_interactions == 6
            graph = await client.get(f"/memory/user/{alice}/graph", headers=headers)
            assert (
                graph.status_code == 200
                and alice + " synthetic" in graph.text
                and bob + " synthetic" not in graph.text
            )
            exported = await client.get(
                f"/privacy/user/{alice}/export", headers=headers
            )
            assert exported.status_code == 200, exported.text
            assert (
                "Synthetic persisted digest" in exported.text
                and bob + " synthetic" not in exported.text
            )
            old_epoch = await capture_memory_epoch(alice)
            erased = await client.post(
                f"/privacy/user/{alice}/erase",
                headers=headers,
                json={"confirmation": "删除我的全部数据"},
            )
            assert (
                erased.status_code == 200 and erased.json()["status"] == "completed"
            ), erased.text
            try:
                async with AsyncSessionLocal() as session:
                    await store_memory(
                        session,
                        MemoryEntry(
                            entry_id="",
                            user_id=alice,
                            category="fact",
                            content="stale queued write",
                            embedding=embedding,
                        ),
                        expected_epoch=old_epoch,
                    )
            except StaleMemoryWriteError:
                pass
            else:
                raise AssertionError("Erasure must reject old queued writes")
            async with AsyncSessionLocal() as session:
                assert await list_user_memories(session, alice) == []
                assert len(await list_user_memories(session, bob)) == 1
            assert await history.get_session_turns(state["session"]) == []
            assert (await store.get_relationship(alice)).total_interactions == 0
            bob_erase = await client.post(
                f"/privacy/user/{bob}/erase",
                headers={"Authorization": "Bearer " + state["keys"][bob]},
                json={"confirmation": "删除我的全部数据"},
            )
            assert (
                bob_erase.status_code == 200
                and bob_erase.json()["status"] == "completed"
            )
        async with AsyncSessionLocal() as session:
            assert not (
                await session.execute(
                    text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
                )
            ).scalar_one()
    print("PostgreSQL reference-host " + name + " phase passed")


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["seed", "verify"])
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args()
    if args.phase:
        asyncio.run(phase(args.phase, args.workspace))
        return
    workspace = Path(tempfile.mkdtemp(prefix="companion-sql-smoke-"))
    configure(workspace)
    users = ["sql-qa-" + uuid4().hex for _ in range(2)]
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
        )
    )
    (workspace / "state.json").write_text(
        json.dumps(
            {"alice": users[0], "bob": users[1], "keys": keys, "session": uuid4().hex}
        )
    )
    for name in ("seed", "verify"):
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--phase",
                name,
                "--workspace",
                str(workspace),
            ],
            check=True,
        )
    print(
        "Actual PostgreSQL/pgvector: host startup, non-superuser writes/search, JSON tags, rollback, restart, "
        "concurrent replay-safe persona, owner isolation, graph/export/erase and stale-write barrier passed"
    )


if __name__ == "__main__":
    run()
