# Development Guide

This is a monorepo with two primary projects:

- **companion-ai/** — Companion AI agent (FastAPI backend, Lite Mode for local dev)
- **hermes-agent/** — Self-improving AI agent framework (Python CLI + gateway)

For hermes-agent development details, see `hermes-agent/AGENTS.md`.

## Cursor Cloud specific instructions

### Environment prerequisites

- Python 3.11 (installed via `uv python install 3.11`)
- `uv` package manager (installed at `~/.local/bin/uv`)
- PATH must include `$HOME/.local/bin`

### companion-ai

- **Venv**: `/workspace/companion-ai/.venv` (Python 3.11)
- **Install**: `cd /workspace/companion-ai && uv pip install -e ".[dev]" && uv pip install aiosqlite`
- **Lint**: `cd /workspace/companion-ai && source .venv/bin/activate && ruff check .`
- **Tests**: `cd /workspace/companion-ai && source .venv/bin/activate && pytest -q --ignore=voice_layer/tests/test_voice.py`
  - The `voice_layer` test file fails to collect due to a missing `numpy` dep (not in base requirements); ignore it.
  - 5 errors in `memory_system/tests/test_memory.py` require a live PostgreSQL+pgvector — expected in Lite Mode.
- **Run (Lite Mode, no Docker needed)**: `cd /workspace/companion-ai && source .venv/bin/activate && COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000`
- **Health check**: `curl http://localhost:8000/health`
- `aiosqlite` must be installed for Lite Mode (SQLite async backend) — it's not in `pyproject.toml` but required at runtime.

### hermes-agent

- **Venv**: `/workspace/hermes-agent/.venv` (Python 3.11)
- **Install**: `cd /workspace/hermes-agent && uv pip install -e ".[all,dev]" && uv pip install pytest-split pip`
- **Lint**: ruff config intentionally excludes all files (`exclude = ["*"]`); lint pass is always clean.
- **Tests**: `cd /workspace/hermes-agent && bash scripts/run_tests.sh tests/<path>` (uses 4 xdist workers, CI-parity env)
  - `scripts/run_tests.sh` needs `chmod +x` if freshly cloned.
  - The script tries to `pip install pytest-split` if missing — having `pip` in the venv avoids errors.
- **CLI**: `cd /workspace/hermes-agent && source .venv/bin/activate && hermes --help`
- Full test suite (~15k tests) takes significant time; use targeted paths for quick iteration.

### Gotchas

- Both projects require Python >= 3.11; Python 3.12 (system default) works for hermes-agent but companion-ai targets 3.11 for consistency.
- `COMPANION_LITE_MODE=true` disables Docker dependencies (PostgreSQL, Redis, Neo4j, Mosquitto) and uses SQLite + in-memory alternatives.
- hermes-agent runtime requires LLM API keys (OPENAI_API_KEY, etc.) to actually chat — tests run without them (blanked by conftest.py).
- companion-ai runtime requires an LLM API key for the orchestrator conversation endpoint, but health/persona/memory endpoints work without one.
