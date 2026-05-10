# Development Guide

This repository now has one active product codebase:

- **companion-ai/** - Companion AI module library and reference app

Historical upstream reference sources such as `hermes-agent/` and
`airi-analysis/` have been removed from this workspace. Do not search for,
import from, test, or modify those directories. If a future task needs upstream
ideas again, fetch or inspect them outside this repository and copy only the
small, reviewed design notes or code snippets that are intentionally adopted.

## Cloud Agent quick-start skill

Cloud Agents joining this repo should read
[`.cursor/skills/cloud-agents/SKILL.md`](.cursor/skills/cloud-agents/SKILL.md)
**first**. It is the minimal runbook for activation, Lite-Mode launch, feature
flags, smoke tests, and companion-ai testing playbooks. Update that skill
whenever you discover a new testing trick or workflow gotcha.

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
  - 5 errors in `memory_system/tests/test_memory.py` require a live PostgreSQL+pgvector - expected in Lite Mode.
- **Fast clean tests**: `cd /workspace/companion-ai && source .venv/bin/activate && pytest -q --ignore=voice_layer/tests/test_voice.py --ignore=memory_system/tests/test_memory.py`
- **Run (Lite Mode, no Docker needed)**: `cd /workspace/companion-ai && source .venv/bin/activate && COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000`
- **Health check**: `curl http://localhost:8000/health`
- **Arch lint**:
  - Install: `cd /workspace/companion-ai && source .venv/bin/activate && uv pip install -e ".[arch]"`
  - Dependency graph and hard-code scan: `python tools/check_arch.py`
  - Check against baseline, fail on new violations: `python tools/check_arch.py --check`
  - import-linter contracts: `lint-imports`
  - Baseline file: `tools/arch_baseline.json`

`aiosqlite` must be installed for Lite Mode (SQLite async backend). It may not
be present in older environments even when the project itself is installed.

### Gotchas

- `COMPANION_LITE_MODE=true` disables Docker dependencies (PostgreSQL, Redis, Neo4j, Mosquitto) and uses SQLite + in-memory alternatives.
- companion-ai runtime requires an LLM API key for the orchestrator conversation endpoint, but health/persona/memory endpoints work without one.
- Keep future third-party upstream projects out of the repo root unless they become intentional product code.
