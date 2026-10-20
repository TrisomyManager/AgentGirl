"""Inspect historical PostgreSQL schema; --apply performs a lossless transaction."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from memory_system.postgres_schema import cli  # noqa: E402

if __name__ == "__main__":
    cli()
