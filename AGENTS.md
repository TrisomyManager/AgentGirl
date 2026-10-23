# Development Guide

This repository uses a **monorepo layout** for the 小暖 Companion AI product:

| Area | Path | Role |
|------|------|------|
| Backend | `apps/backend/` | FastAPI monolith + Python modules (`main.py`, `pyproject.toml`) |
| Web | `apps/web/` | Vue 3 + Vite reference UI |
| PC client | `apps/pc-client/` | Electron/Vue, device bridge, optional desktop pet |
| Contracts | `packages/contracts/` | Cross-end schema / API changelog (non-runtime) |
| Integration | `integration/` | PowerShell dev/smoke scripts |

Legacy path bookmark: `companion-ai/README.md` points to the above.

Historical upstream reference sources such as `hermes-agent/` and `airi-analysis/` have been removed from this workspace. Do not search for, import from, test, or modify those directories. **Do not add AIRI, Hermes, OpenTalking, or other full external trees** into this repo.

## Cloud Agent quick-start skill

Cloud Agents joining this repo should read [`.cursor/skills/cloud-agents/SKILL.md`](.cursor/skills/cloud-agents/SKILL.md) **first**.

## Cursor Cloud specific instructions

### Environment prerequisites

- Python 3.11 (installed via `uv python install 3.11`)
- `uv` package manager (installed at `~/.local/bin/uv`)
- PATH must include `$HOME/.local/bin`

### Backend (`apps/backend`)

- **Venv**: `/workspace/apps/backend/.venv`（本地同理：`apps/backend/.venv`）。
- **Install**: `cd /workspace/apps/backend && uv pip install -e ".[dev]" && uv pip install aiosqlite`
- **Lint**: `cd /workspace/apps/backend && source .venv/bin/activate && ruff check .`
- **Tests**: `cd /workspace/apps/backend && source .venv/bin/activate && pytest -q --ignore=voice_layer/tests/test_voice.py`
  - The `voice_layer` test file fails to collect due to a missing `numpy` dep in some images; ignore it.
  - 5 errors in `memory_system/tests/test_memory.py` require PostgreSQL+pgvector — expected in Lite Mode.
- **Fast clean tests**: `cd /workspace/apps/backend && source .venv/bin/activate && pytest -q --ignore=voice_layer/tests/test_voice.py --ignore=memory_system/tests/test_memory.py`
- **Run (Lite Mode)**: `cd /workspace/apps/backend && source .venv/bin/activate && COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000`
- **Health check**: `curl http://localhost:8000/health`
- **Arch lint**:
  - Install: `cd /workspace/apps/backend && source .venv/bin/activate && uv pip install -e ".[arch]"`
  - `python tools/check_arch.py` / `python tools/check_arch.py --check`
  - `lint-imports`
  - Baseline: `tools/arch_baseline.json`

`aiosqlite` must be installed for Lite Mode (SQLite async backend).

### Gotchas

- `COMPANION_LITE_MODE=true` disables Docker dependencies and uses SQLite + in-memory alternatives. `device_coordination` stays enabled; smoke with `apps/pc-client/legacy_python/sim_client.py` (requires `httpx`) or `integration/scripts/smoke-device-flow.ps1` on Windows.
- Internal HTTP clients use `COMPANION_SELF_BASE_URL` when set; otherwise `http://127.0.0.1:{COMPANION_SERVICE_PORT}` (default `8000`).
- Orchestrator conversation endpoints need an LLM API key; health/persona/memory endpoints work without one.
- **Device Gateway** is a backend capability; the Electron PC client contains its existing device bridge. Legacy Python simulators live in `apps/pc-client/legacy_python/`.

### Web (`apps/web`)

```bash
cd apps/web
npm install
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

### Integration

See [`integration/README.md`](integration/README.md).

### Desktop pet and proactive context

- Read [`apps/backend/docs/dsh-pet-adoption.md`](apps/backend/docs/dsh-pet-adoption.md) for setup, consent, feature activation and compatibility limits.
- PC build: `cd apps/pc-client && npm ci && npm run build`; pack tests: `npm run test:pet` (Node 22.23/24.19 verified). Native Electron UI requires a desktop session; headless builds do not validate Windows transparency, DPI or packaging.
- Web build: `cd apps/web && npm ci && npm run build`.
- New backend regression tests live in `action_executor/tests/test_desktop_companion.py`, `action_executor/tests/test_companion_integration.py`, `memory_system/tests/test_lexical_recall.py` and `shared_runtime/tests/test_{features,memory_prompt_budget}.py`. Include them in the fast clean suite above.
- Feature selection is a startup snapshot in `shared_runtime/features.py`. Saves are pending until restart; desktop context additionally requires per-user consent and a process allowlist. Keep optional core/Qt trees and upstream character assets out of the repository.
- Proactive desktop observations are process metadata only, not screenshots/titles. The local helper is private IPC, never a registered device tool. Pet rendering cannot own persona, memory, LLM or tool decisions.
- Architecture/lint failures must be compared against the unchanged base; do not silently reset baselines. Vitest currently can stall during teardown after reporting assertions in this headless environment; report this separately from passing builds.
