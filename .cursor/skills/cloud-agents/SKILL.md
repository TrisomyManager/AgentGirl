---
name: cloud-agents-starter
description: "Cloud-agent starter runbook: how to set up, run, test, and iterate on this monorepo (companion-ai + hermes-agent). Read this first when you join a Cloud Agent task."
version: 1.0.0
metadata:
  cursor:
    audience: cloud-agents
    tags: [runbook, setup, testing, companion-ai, hermes-agent]
---

# Cloud Agent Starter Runbook

This is the first thing a Cloud Agent should read when starting work in this
monorepo. It is intentionally short and biased toward **commands you can copy
verbatim**. For deeper architectural background, follow the cross-references at
the bottom of each section.

The repo contains two top-level Python projects:

| Area | Path | Role |
|---|---|---|
| companion-ai | `companion-ai/` | FastAPI companion app (active development) |
| hermes-agent | `hermes-agent/` | Self-improving CLI agent + gateway (stable base) |

The Cloud Agent VM is preconfigured by `AGENTS.md`:
- Python 3.11 lives at `~/.local/share/uv/python/...` (managed by `uv`)
- `uv` is installed at `~/.local/bin/uv`
- Both projects already have `.venv/` populated on a fresh VM

Always assume **no Docker, no Postgres, no Redis, no internet creds** unless
the user has wired up secrets. Work in Lite Mode where possible.

---

## 0. Pre-flight (do this once per task)

```bash
# Confirm the venvs and uv are present.
ls /workspace/companion-ai/.venv/bin/python
ls /workspace/hermes-agent/.venv/bin/python
which uv

# Make sure `uv` is on PATH for any pip installs you have to add.
export PATH="$HOME/.local/bin:$PATH"
```

If a venv is missing, recreate it from `AGENTS.md`:
- companion-ai: `cd /workspace/companion-ai && uv pip install -e ".[dev]" && uv pip install aiosqlite`
- hermes-agent: `cd /workspace/hermes-agent && uv pip install -e ".[all,dev]" && uv pip install pytest-split pip`

There is **no login step** for either project. LLM access happens via env vars
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) which Cloud Agents inject from
Dashboard secrets. If those are absent, the chat endpoints will 401/500 but
health, memory, persona, and the test suite still work — that is the
intended Lite-Mode workflow.

---

## 1. companion-ai

Backend: FastAPI monolith (`main.py`) that mounts every module's router into
one process. The default Cloud-Agent workflow is **Lite Mode** — SQLite +
in-memory replacements for Postgres/Neo4j/Redis/MQTT — no Docker required.

### 1a. Activate

```bash
cd /workspace/companion-ai
source .venv/bin/activate
```

### 1b. Feature flags & env you can set or mock

All flags are read by `shared/config.py` (Pydantic Settings, env prefix
`COMPANION_`). The ones you actually touch from a Cloud Agent:

| Env var | What it does | Default for cloud |
|---|---|---|
| `COMPANION_LITE_MODE` | SQLite + in-memory; disables Docker deps | `true` |
| `COMPANION_MONOLITHIC` | In-process module calls vs. HTTP. Set automatically by `main.py`. | `true` |
| `COMPANION_ENABLE_VOICE` | Mount voice router (needs `numpy` etc.) | `false` for fast tests |
| `COMPANION_ENABLE_ACTION_2D` | Mount 2D action layer | `false` for fast tests |
| `COMPANION_ENABLE_DEVICE_COORDINATION` | MQTT device bus | auto-`false` in Lite Mode |
| `COMPANION_ENABLE_MEMORY_PIPELINE` | Background memory consolidation | `true` |
| `COMPANION_LOG_LEVEL` | `INFO`/`DEBUG`/... | `INFO` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | LLM access for `/orchestrator/turn*` | unset → 500 on chat endpoints |

`scripts/start_lite_server.py` is the canonical "minimal Lite-Mode launcher" —
it sets the four `COMPANION_ENABLE_*` toggles defensively before importing
`main`.

### 1c. Run the app

```bash
# Recommended: minimal Lite-Mode server (sets sane defaults)
cd /workspace/companion-ai && source .venv/bin/activate
COMPANION_LITE_MODE=true python scripts/start_lite_server.py
```

Or directly through uvicorn:

```bash
COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000
```

Use a tmux session (`tmux -f /exec-daemon/tmux.portal.conf new-session -d -s companion-server ...`)
so you can leave it running and inspect logs from another shell.

### 1d. Smoke-test the running server

```bash
# Health (always works in Lite Mode)
curl -s http://127.0.0.1:8000/health | jq .

# Module-level statuses (used by the frontend status panel)
curl -s http://127.0.0.1:8000/orchestrator/project_status | jq '.modules | keys'
curl -s http://127.0.0.1:8000/orchestrator/settings/llm | jq .
```

If you have an `OPENAI_API_KEY` configured, the end-to-end memory recall
smoke test is:

```bash
cd /workspace/companion-ai && source .venv/bin/activate
python scripts/smoke_lite_chat.py
```

It boots its own server on port 8000, sends two `/orchestrator/turn` calls in
the same session, and asserts the second reply mentions details from the
first turn.

### 1e. Tests

```bash
cd /workspace/companion-ai && source .venv/bin/activate
pytest -q --ignore=voice_layer/tests/test_voice.py
```

Expected outcome on a clean Cloud Agent VM:
- `voice_layer/tests/test_voice.py` — **must be excluded** (missing `numpy`
  collection error otherwise).
- 5 errors in `memory_system/tests/test_memory.py` — **expected** in Lite
  Mode (they need a live Postgres + pgvector). Filter with
  `--ignore=memory_system/tests/test_memory.py` if you want a clean exit.
- All other tests pass (~105 tests, ~20s wall time).

`conftest.py` at the project root force-sets `COMPANION_LITE_MODE=true`
before any test imports — never remove that line, or memory_system tests
will try to open a real Postgres socket at collection time.

The fast iteration command (clean output, no Postgres errors):

```bash
pytest -q \
  --ignore=voice_layer/tests/test_voice.py \
  --ignore=memory_system/tests/test_memory.py
```

### 1f. Frontend (`frontend_app/`)

Vue 3 + Vite. **Don't run `npm install` blindly** — it pulls a lot. Only
run it when the change you're making touches `frontend_app/` or you need
to verify a UI bug. Build process:

```bash
cd /workspace/companion-ai/frontend_app
npm install            # only first time / on package.json changes
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev    # http://localhost:5173
```

For UI changes, prefer the `computerUse` subagent against the running
`npm run dev` server instead of the static frontend tests.

### 1g. Cross-references

- `companion-ai/AGENTS.md` is the system prompt's source of truth for env
  prereqs — anything you add to this skill that conflicts with it is
  wrong.
- `companion-ai/README.md` — full architecture, microservice mode, frontend
  Live2D notes (Chinese).
- `companion-ai/MODULE_CONTRACTS.md` — module-to-module API contracts.
- `companion-ai/main.py:_ENABLED_MODULES` — authoritative list of toggles
  applied at startup.

---

## 2. hermes-agent

Python CLI + messaging gateway. Runtime requires LLM API keys to actually
chat; tests scrub all credentials and run hermetically.

### 2a. Activate & smoke check

```bash
cd /workspace/hermes-agent
source .venv/bin/activate
hermes --help                    # confirms the venv works
hermes doctor                    # verifies env, paths, providers
```

`HERMES_HOME` defaults to `~/.hermes/` and is **per-profile** — never
hardcode `~/.hermes` in code. See `hermes-agent/AGENTS.md` "Profiles"
section for the rules.

### 2b. Login / API keys

There is no interactive login from a Cloud Agent. Either:
1. The user added secrets in the Cursor Dashboard (`OPENAI_API_KEY`, etc.)
   and they're injected as env vars on VM start — `hermes` picks them up.
2. Or you're working on tests / lint / refactors — keys are not needed.

To inspect what hermes thinks is configured without leaking secrets:

```bash
hermes status
hermes config show               # prints config.yaml (NO secrets)
```

### 2c. Run an interactive chat

```bash
cd /workspace/hermes-agent && source .venv/bin/activate
hermes chat                      # prompt_toolkit CLI
hermes chat --tui                # Ink (Node) TUI; needs `npm install` in ui-tui/ first
hermes chat -z "hello"           # one-shot prompt
```

For Cloud-Agent automation, prefer `-z "<prompt>"` over interactive mode —
the agent loop runs once and exits.

### 2d. Feature flags & env

Hermes reads most settings from `~/.hermes/config.yaml`. The few env vars
you'll touch from a Cloud Agent:

| Env var | Effect |
|---|---|
| `HERMES_HOME` | Override profile root (the test harness sets this to a tmpdir). |
| `HERMES_TUI=1` | Force TUI mode on `hermes chat`. |
| `HERMES_BACKGROUND_NOTIFICATIONS` | `all`/`result`/`error`/`off` — gateway background-process verbosity. |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc. | Provider creds. |

To **mock** an LLM response (e.g. for a regression test that exercises the
agent loop without burning credits), patch `agent.providers` rather than
setting fake env vars — see `tests/agent/test_chat_completions.py` for
canonical mocks.

### 2e. Tests — ALWAYS use the wrapper

```bash
cd /workspace/hermes-agent
chmod +x scripts/run_tests.sh   # only on a fresh clone; then:
bash scripts/run_tests.sh tests/<path>      # subdirectory
bash scripts/run_tests.sh tests/agent/test_foo.py::test_x   # one test
bash scripts/run_tests.sh                   # full suite (~15k tests, slow)
```

Why the wrapper matters (per `hermes-agent/AGENTS.md`):
- Unsets every `*_API_KEY`/`*_TOKEN`/`*_SECRET` in env (CI parity).
- Forces `TZ=UTC`, `LANG=C.UTF-8`, `PYTHONHASHSEED=0`.
- Pins `-n 4` xdist workers (Cloud VMs may have many more cores —
  `-n auto` causes ordering flakes).
- Activates `.venv/` automatically.

**Never** call `pytest` directly in hermes-agent — `tests/conftest.py`
provides the same hermetic guards via an autouse fixture, but the wrapper
is belt-and-suspenders. For quick iteration on Cloud:

```bash
bash scripts/run_tests.sh tests/hermes_cli/ -q
```

Full suite (~15k tests) takes substantial time even with `-n 4`; only run
it before pushing a substantive change.

### 2f. Lint

`ruff` is configured with `exclude = ["*"]` — running `ruff check .` is
always green. Don't add lint-only commits.

### 2g. Cross-references

- `hermes-agent/AGENTS.md` — definitive testing/contributing guide, profile
  rules, plugin architecture, slash-command registry. Read before editing
  `cli.py`, `run_agent.py`, or `gateway/`.
- `hermes-agent/CONTRIBUTING.md` — PR workflow.
- `hermes-agent/scripts/run_tests.sh` — the wrapper itself; check the
  comment block at the top for the full env list it scrubs.

---

## 3. End-to-end test playbooks

Pick the playbook that matches the change you made.

### 3a. Backend bug fix in companion-ai (no UI)

1. `cd /workspace/companion-ai && source .venv/bin/activate`
2. Add or update a pytest under the affected module's `tests/` dir.
3. Run the fast subset:
   ```bash
   pytest -q --ignore=voice_layer/tests/test_voice.py \
             --ignore=memory_system/tests/test_memory.py
   ```
4. Boot Lite Mode and `curl` the endpoint(s) you touched:
   ```bash
   COMPANION_LITE_MODE=true python scripts/start_lite_server.py &
   curl -s http://127.0.0.1:8000/<your-endpoint> | jq .
   ```
5. Stop the server with the recorded PID; do NOT use `pkill -f`.

### 3b. UI change in companion-ai

1. Run the backend in Lite Mode (3a steps 1, 4).
2. `cd frontend_app && VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev`
3. Use the `computerUse` subagent against `http://localhost:5173` to take
   before/after screenshots. Record a video walkthrough for the PR.
4. If you touched shared TypeScript types in `frontend_sdk/`, also run
   `cd frontend_sdk && npm run build`.

### 3c. Bug fix in hermes-agent

1. `cd /workspace/hermes-agent && source .venv/bin/activate`
2. Run the targeted test path you expect to break/pass:
   ```bash
   bash scripts/run_tests.sh tests/<area>/test_<file>.py -q
   ```
3. If the change touches CLI dispatch / gateway / prompts, also run a tiny
   one-shot smoke without keys:
   ```bash
   HERMES_HOME=$(mktemp -d) hermes -z "say hi" 2>&1 | head -20
   ```
   (It will fail to call an LLM but exercises argparse + provider selection
   + skill loading.)
4. Before pushing: `bash scripts/run_tests.sh tests/<changed-area>/`
   covering at least the directories you touched.

### 3d. Cross-project change

Run **both** test commands. They are independent; failures in one do not
block the other.

---

## 4. Common gotchas (read before debugging)

- **`aiosqlite` missing.** companion-ai's Lite Mode requires it but it's
  not in `pyproject.toml`. `uv pip install aiosqlite` into the
  companion-ai venv.
- **`numpy` missing → `voice_layer` test collection fails.** Always pass
  `--ignore=voice_layer/tests/test_voice.py` unless you're working on
  voice.
- **PostgreSQL errors at companion-ai test startup.** You forgot
  `COMPANION_LITE_MODE=true`, or you ran tests after a code path imported
  `memory_system` modules that cached a non-Lite settings object. Fix:
  ensure `conftest.py` is intact, restart pytest fresh.
- **hermes tests fail locally but pass in CI (or vice versa).** You ran
  `pytest` directly. Use `bash scripts/run_tests.sh ...` instead.
- **Hermes profile pollution.** Tests must never read/write your real
  `~/.hermes/`. The autouse `_isolate_hermes_home` fixture redirects
  `HERMES_HOME` to a tmpdir; never bypass it.
- **`pkill -f`.** Forbidden by Cloud Agent rules and breaks shared VMs.
  Track the PID you started (`echo $! > /tmp/foo.pid`) and `kill $(cat
  /tmp/foo.pid)`.
- **`COMPANION_MONOLITHIC` is set automatically.** Don't unset it for
  Lite-Mode local dev — it's what makes the in-process router work
  without HTTP loopback calls.
- **LLM-dependent endpoints in companion-ai.** `/orchestrator/turn` and
  `/orchestrator/turn/stream` need a real key. `/health`,
  `/orchestrator/project_status`, `/orchestrator/settings/*`, persona, and
  memory endpoints all work without one.
- **Frontend `npm install` is heavy.** Skip it unless you actually need
  the dev server.

---

## 5. Updating this skill

This skill exists so the next Cloud Agent doesn't have to rediscover the
same setup tricks. **Whenever you discover something that would have
saved you time, add it.**

### When to edit this file

- A command in the runbook produced a different result than documented
  (either the docs lied or the env changed).
- You found a new feature flag, env var, or undocumented endpoint that
  matters during testing.
- You worked around a missing dependency, race, or sequencing issue that
  isn't called out in the "Gotchas" section.
- A new top-level project (alongside `companion-ai/` and `hermes-agent/`)
  was added, or a project's runbook diverged enough to need its own
  section.

### How to edit it (rules)

1. **Keep it short.** Each section is meant to fit on a screen. If a
   detail belongs in 200 lines of prose, link to the architecture doc and
   leave a one-line summary here.
2. **Every command must be copy-pasteable** and start from a known cwd.
   Don't write half-shell-pseudocode.
3. **Verify before committing.** Run the new command on the Cloud VM
   exactly as written. If it requires a feature flag, document the flag.
4. **Prefer additions over rewrites.** If a section is now wrong but other
   agents may have memorized the old version, leave a clear "as of
   YYYY-MM-DD" note at the top of the section explaining what changed.
5. **Sync cross-references.** If you change something that's also in
   `AGENTS.md`, `companion-ai/AGENTS.md`, or `hermes-agent/AGENTS.md`,
   update both. Those files are the contract; this skill is the
   onboarding sleeve.
6. **Don't paste secrets.** Reference env var names, not values. Cloud
   Agent secrets live in the Cursor Dashboard, never in Git.
7. **Open a PR.** Even tiny doc tweaks go through normal review so other
   agents see the diff in `git log`.

### Suggested PR title format

```
docs(skill): cloud-agents — <one-line change>
```

### Where related guidance lives

- `AGENTS.md` (repo root) — Cloud-Agent VM setup contract. **Authoritative
  for env prerequisites.** This skill must agree with it.
- `companion-ai/AGENTS.md` — none yet; rules currently live in the root
  AGENTS.md `### companion-ai` section.
- `hermes-agent/AGENTS.md` — authoritative for hermes-agent architecture,
  testing, plugins, profiles, and policies. This skill defers to it.
- `hermes-agent/skills/` — example of an in-repo skill format if you want
  to graduate this runbook to per-project skills.
