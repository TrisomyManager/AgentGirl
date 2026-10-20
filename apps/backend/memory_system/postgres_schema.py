"""Lossless, explicit migration of historical PostgreSQL memory bootstrap tables."""

from sqlalchemy import text


async def migration_plan(connection, dimension: int) -> list[str]:
    if not 1 <= dimension <= 2000:
        raise ValueError("Embedding dimension must be between 1 and 2000")
    rows = (
        (
            await connection.execute(
                text(
                    "SELECT c.relname AS table_name, a.attname AS column_name, "
                    "format_type(a.atttypid, a.atttypmod) AS column_type, a.attnotnull AS required "
                    "FROM pg_attribute a JOIN pg_class c ON a.attrelid=c.oid "
                    "JOIN pg_namespace n ON c.relnamespace=n.oid "
                    "WHERE n.nspname=current_schema() AND c.relname IN ('memories','users') "
                    "AND a.attnum>0 AND NOT a.attisdropped"
                )
            )
        )
        .mappings()
        .all()
    )
    statements = []
    for row in rows:
        table, column, kind = row["table_name"], row["column_name"], row["column_type"]
        if table == "memories" and column == "embedding":
            target = f"vector({dimension})"
            if kind in {"text", "character varying", "vector"}:
                statements.append(
                    f"ALTER TABLE memories ALTER COLUMN embedding TYPE {target} USING embedding::{target}"
                )
            elif kind != target:
                raise RuntimeError("Embedding dimensions differ; back up and explicitly re-embed before migration")
        elif table == "memories" and column == "emotion_tags" and kind in {"text[]", "character varying[]"}:
            statements.extend(
                [
                    "ALTER TABLE memories ALTER COLUMN emotion_tags DROP DEFAULT",
                    "ALTER TABLE memories ALTER COLUMN emotion_tags TYPE json USING to_json(emotion_tags)",
                    "ALTER TABLE memories ALTER COLUMN emotion_tags SET DEFAULT '[]'::json",
                ]
            )
        elif ((table == "memories" and column == "entry_id") or (table == "users" and column == "user_id")) and row[
            "required"
        ]:
            # Preserve all old values and uniqueness. New runtime rows use the
            # canonical id/user_profiles tables and need no invented legacy ID.
            statements.append(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL")
    return statements


async def migrate(connection, dimension: int, *, apply: bool = False) -> list[str]:
    await connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(current_schema() || '.companion.schema'))"))
    plan = await migration_plan(connection, dimension)
    if apply:
        for statement in plan:
            await connection.execute(text(statement))
    return plan


def cli():
    """Available from installed wheels as python -m memory_system.postgres_schema."""
    import argparse
    import asyncio
    import json

    from shared_runtime.config import get_settings
    from shared_runtime.database import close_database, engine

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply after backing up; default only lists changes")
    args = parser.parse_args()
    settings = get_settings()
    if settings.lite_mode:
        raise SystemExit("Use COMPANION_LITE_MODE=false and a dedicated PostgreSQL URL; back up before --apply")

    async def execute():
        try:
            async with engine.begin() as connection:
                plan = await migrate(connection, settings.embedding_dim, apply=args.apply)
            print(json.dumps({"applied": args.apply, "changes": plan}, ensure_ascii=False))
        finally:
            await close_database()

    asyncio.run(execute())


if __name__ == "__main__":
    cli()
