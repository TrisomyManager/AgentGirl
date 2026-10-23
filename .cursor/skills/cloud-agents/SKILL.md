---
name: cloud-agents-starter
description: "Cloud-agent starter runbook for companion-ai. Read this first when joining the repo."
version: 2.2.0
metadata:
  cursor:
    audience: cloud-agents
    tags: [runbook, setup, testing, companion-ai]
---

# Cloud Agent Starter Runbook

This repository uses a **monorepo** for 小暖 Companion AI:

| Area | Path |
|------|------|
| Backend | `apps/backend/` |
| Web | `apps/web/` |
| Electron PC client | `apps/pc-client/` |
| Contracts (draft) | `packages/contracts/` |
| Integration scripts | `integration/` |

Legacy bookmark: `companion-ai/README.md` → new paths.

Historical upstream (`hermes-agent/`, `airi-analysis/`) was removed. Do not search or test those paths. **Do not import AIRI/Hermes/OpenTalking source trees.**

Always assume **no Docker, no Postgres, no Redis, no internet creds** unless the user wired secrets. Work in Lite Mode where possible.

---

## 0. Pre-flight

```bash
ls /workspace/apps/backend/.venv/bin/python
which uv
export PATH="$HOME/.local/bin:$PATH"
```

Do **not** use `companion-ai/frontend_app` or `companion-ai/examples/device_client`; use `apps/web` and `apps/pc-client`. The `companion-ai/README.md` file is only a legacy bookmark.

If the venv is missing:

```bash
cd /workspace/apps/backend
uv pip install -e ".[dev]"
uv pip install aiosqlite
```

LLM access: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc. If absent, chat may fail; health, memory, persona, and most tests often still pass.

---

## 1. Run backend

```bash
cd /workspace/apps/backend
source .venv/bin/activate
COMPANION_LITE_MODE=true python scripts/start_lite_server.py
```

Or:

```bash
COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000
```

Health:

```bash
curl -s http://127.0.0.1:8000/health | jq .
curl -s http://127.0.0.1:8000/orchestrator/project_status | jq '.modules | keys'
```

If `OPENAI_API_KEY` is configured:

```bash
python scripts/smoke_lite_chat.py
```

---

## 2. Tests

```bash
cd /workspace/apps/backend
source .venv/bin/activate
pytest -q --ignore=voice_layer/tests/test_voice.py
```

Fast clean:

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

Vue 3 + Vite: `apps/web/`.

```bash
cd /workspace/apps/web
npm install
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Run `npm install` when changing `apps/web/` or verifying UI.

### Device gateway smoke (Lite Mode)

With backend on port 8000:

1. Optional: `cd apps/pc-client/legacy_python && pip install httpx && python sim_client.py` (set `XIAONUAN_API_BASE_URL` if needed).
2. UI: capabilities → **我的设备**, or `POST /device/send_command` with `{"user_id":"…","command":"ping"}` and confirm the sim logs execution + `command_result`.

On Windows, `integration/scripts/smoke-device-flow.ps1` covers register → heartbeat → send → claim → mark_running → result → audit.

---

## 4. Documentation

- `AGENTS.md` — root development guide
- `README.md` — monorepo map
- `apps/backend/README.md` — backend overview
- `apps/backend/ARCHITECTURE.md` — architecture
- `apps/backend/MODULE_CONTRACTS.md` — module contracts
- `apps/backend/main.py:_ENABLED_MODULES` — startup toggles
- `integration/README.md` — triage IDs + smoke scripts

When adding a workflow, update this skill and `AGENTS.md`.

## 5. Desktop companionship workflow

Read [`apps/backend/docs/dsh-pet-adoption.md`](../../../apps/backend/docs/dsh-pet-adoption.md) from the repository root. Electron/Vue now provides the optional transparent pet window; the Python simulator remains in `apps/pc-client/legacy_python/`.

```bash
cd apps/pc-client
npm ci
npm run build
npm run test:pet
```

Node 22.23 and 24.19 were verified. Web builds separately with `cd apps/web && npm ci && npm run build`. Native desktop UI and Windows helper behavior require a real Windows session; do not equate headless compilation with desktop acceptance.

Run the fast clean backend suite in section 2, which includes the new context, policy persistence, deferred memory, lexical recall, prompt budget and feature registry regression tests. Do not copy upstream Qt sources, OCR models or character assets into this repository. The new pet adapter accepts user-selected WebM/GIF source packs and must remain presentation-only.

Use `COMPANION_FEATURE_CONFIG_PATH` for isolated test settings. Global feature updates are frozen for the running process and apply on restart. Desktop metadata sampling also needs explicit per-user consent; keep it disabled by default. The Windows helper is a private fixed IPC invocation, not a remotely callable tool.

If full-repository lint/architecture checks fail, compare unchanged base violations and record the delta without changing baseline policy. In the current headless environment Vitest may report passing assertions then stall at teardown; report that limitation without calling the entire suite green.
