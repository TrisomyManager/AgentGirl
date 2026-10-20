"""Test legacy schema conversion and failure rollback against real PostgreSQL.

Uses isolated schemas in COMPANION_TEST_POSTGRES_URL. The same explicit QA
database guard as smoke_postgres applies; no existing schemas are altered.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from uuid import uuid4

from smoke_postgres import configure


async def main():
    configure(Path(tempfile.mkdtemp(prefix="companion-migration-smoke-")))
    from sqlalchemy import delete, select, text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import AsyncSession

    from core_orchestrator.privacy import _legacy_user_condition
    from memory_system.postgres_schema import migrate, migration_plan
    from shared_runtime.database import close_database, engine

    vector = "[" + ",".join(["0.1"] * 1024) + "]"
    try:
        for valid in (True, False):
            schema = "migration_qa_" + uuid4().hex
            # Outer rollback removes the entire synthetic schema, including on
            # assertion failure. The savepoint verifies failed migration rollback.
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                    await connection.execute(
                        text(f'SET LOCAL search_path TO "{schema}", public')
                    )
                    await connection.execute(
                        text(
                            "CREATE TABLE users (id uuid PRIMARY KEY, user_id text UNIQUE NOT NULL, "
                            "profile_json json, created_at timestamptz)"
                        )
                    )
                    await connection.execute(
                        text(
                            "CREATE TABLE memories (id uuid PRIMARY KEY, entry_id text UNIQUE NOT NULL, "
                            "emotion_tags text[] DEFAULT '{}', embedding text, content text)"
                        )
                    )
                    identifier = uuid4()
                    await connection.execute(
                        text(
                            "INSERT INTO memories VALUES "
                            "(:id, 'legacy-alias', ARRAY['happy','calm'], :vector, 'synthetic legacy')"
                        ),
                        {
                            "id": identifier,
                            "vector": vector if valid else "invalid-vector",
                        },
                    )
                    plan = await migrate(connection, 1024)
                    assert len(plan) == 6
                    assert (
                        await connection.scalar(
                            text(
                                "SELECT data_type FROM information_schema.columns "
                                "WHERE table_schema=current_schema() AND table_name='memories' "
                                "AND column_name='embedding'"
                            )
                        )
                        == "text"
                    )
                    if valid:
                        await migrate(connection, 1024, apply=True)
                        row = (
                            await connection.execute(
                                text(
                                    "SELECT id,entry_id,emotion_tags,embedding::text,content FROM memories"
                                )
                            )
                        ).one()
                        tags = json.loads(row[2]) if isinstance(row[2], str) else row[2]
                        assert (
                            row[0] == identifier
                            and row[1] == "legacy-alias"
                            and tags == ["happy", "calm"]
                        )
                        assert (
                            len(json.loads(row[3])) == 1024
                            and row[4] == "synthetic legacy"
                        )
                        assert await migration_plan(connection, 1024) == []
                        await connection.execute(
                            text(
                                "INSERT INTO memories(id,emotion_tags,embedding) VALUES (:id,'[]',:vector)"
                            ),
                            {"id": uuid4(), "vector": vector},
                        )
                        await connection.execute(
                            text(
                                "INSERT INTO users(id,user_id) VALUES (:id,'legacy-alice'),(:other,'legacy-bob')"
                            ),
                            {"id": identifier, "other": uuid4()},
                        )
                        async with AsyncSession(bind=connection) as session:
                            users, condition = await _legacy_user_condition(
                                session, "legacy-alice"
                            )
                            assert (
                                await session.scalar(
                                    select(users.c.id).where(condition)
                                )
                                == identifier
                            )
                            await session.execute(delete(users).where(condition))
                            await session.commit()
                        assert (
                            await connection.scalar(text("SELECT user_id FROM users"))
                            == "legacy-bob"
                        )
                    else:
                        savepoint = await connection.begin_nested()
                        try:
                            await migrate(connection, 1024, apply=True)
                        except DBAPIError:
                            await savepoint.rollback()
                        else:
                            raise AssertionError(
                                "Invalid old vectors must fail migration"
                            )
                        assert await migration_plan(connection, 1024) == plan
                        assert (
                            await connection.scalar(
                                text("SELECT embedding FROM memories")
                            )
                            == "invalid-vector"
                        )
                        await connection.execute(
                            text("UPDATE memories SET embedding=NULL")
                        )
                        await connection.execute(
                            text(
                                "ALTER TABLE memories ALTER COLUMN embedding TYPE vector(3) USING embedding::vector(3)"
                            )
                        )
                        try:
                            await migration_plan(connection, 1024)
                        except RuntimeError:
                            pass
                        else:
                            raise AssertionError(
                                "A different configured dimension must require explicit re-embedding"
                            )
                finally:
                    await transaction.rollback()
        print(
            "Actual PostgreSQL migration: dry-run, retained IDs/content/vectors/tags, nullable legacy aliases, "
            "idempotence, invalid-value rollback and dimension mismatch refusal passed"
        )
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
