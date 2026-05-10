---
name: cloud-agents-starter
description: "Cloud-agent starter runbook for companion-ai. Read this first when joining the repo."
version: 2.0.0
metadata:
  cursor:
    audience: cloud-agents
    tags: [runbook, setup, testing, companion-ai]
---

# Cloud Agent Starter Runbook

This repository has one active codebase:

| Area | Path | Role |
|---|---|---|
| companion-ai | `companion-ai/` | Companion AI module library and reference app |

Historical upstream reference sources (`hermes-agent/`, `airi-analysis/`) were
removed because they made every task burn context on inactive code. Do not
search for, test, or modify those directories.

Always assume **no Docker, no Postgres, no Redis, no internet creds** unless
the user has wired up secrets. Work in Lite Mode where possible.

---

## 0. Pre-flight

```bash
ls /workspace/companion-ai/.venv/bin/python
which uv
export PATH="$HOME/.local/bin:$PATH"
```

If the venv is missing:

```bash
cd /workspace/companion-ai
uv pip install -e ".[dev]"
uv pip install aiosqlite
```

There is no login step. LLM access happens via env vars
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) injected by the environment. If absent,
chat endpoints may fail, but health, memory, persona, and most tests still work.

---

## 1. Run companion-ai

```bash
cd /workspace/companion-ai
source .venv/bin/activate
COMPANION_LITE_MODE=true python scripts/start_lite_server.py
```

Or directly:

```bash
COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000
```

Health checks:

```bash
curl -s http://127.0.0.1:8000/health | jq .
curl -s http://127.0.0.1:8000/orchestrator/project_status | jq '.modules | keys'
curl -s http://127.0.0.1:8000/orchestrator/settings/llm | jq .
```

If `OPENAI_API_KEY` is configured:

```bash
python scripts/smoke_lite_chat.py
```

---

## 2. Tests

Full companion-ai test command:

```bash
cd /workspace/companion-ai
source .venv/bin/activate
pytest -q --ignore=voice_layer/tests/test_voice.py
```

Expected caveats on a clean Cloud Agent VM:

- `voice_layer/tests/test_voice.py` must be excluded if `numpy` is missing.
- `memory_system/tests/test_memory.py` has 5 expected collection/runtime errors in Lite Mode because it needs PostgreSQL + pgvector.

Fast clean command:

```bash
pytest -q \
  --ignore=voice_layer/tests/test_voice.py \
  --ignore=memory_system/tests/test_memory.py
```

Architecture checks:

```bash
python tools/check_arch.py
python tools/check_arch.py --check
lint-imports
```

---

## 3. Frontend

Vue 3 + Vite lives in `companion-ai/frontend_app/`.

```bash
cd /workspace/companion-ai/frontend_app
npm install
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Only run `npm install` when the change touches `frontend_app/` or you need a UI
verification loop.

---

## 4. Documentation

Primary references:

- `AGENTS.md` - root development guide
- `companion-ai/README.md` - project overview
- `companion-ai/ARCHITECTURE.md` - architecture
- `companion-ai/MODULE_CONTRACTS.md` - module contracts
- `companion-ai/main.py:_ENABLED_MODULES` - authoritative startup module toggles

When adding a new workflow, update this skill and the root `AGENTS.md`.
