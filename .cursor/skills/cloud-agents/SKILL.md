---
name: cloud-agents-starter
description: "Cloud-agent starter runbook for companion-ai. Read this first when joining the repo."
version: 2.1.0
metadata:
  cursor:
    audience: cloud-agents
    tags: [runbook, setup, testing, companion-ai]
---

# Cloud Agent Starter Runbook

Latest V2.27: 6.3 accepted after actual GitHub Linux CI and Docker smoke; 36/38 accepted (95%). All currently executable planned functionality is handled. Two explicit user deferrals remain: 6.2 real social-account validation (implementation/local protocol/SDK done, no accounts provided), and 8.6 3D development (discuss and confirm the technical approach after other work, never start automatically). Draft PR10: https://github.com/TrisomyManager/AgentGirl/pull/10; successful run39377276774 at a164ab41a7fa73d24fdb848472850803e245dddb. Linux backend839 (67.24s, strict thread/unraisable warnings), desktop tools16, Web86, both clients tests/audit/builds, 6 import contracts, wheel artifact, actual PostgreSQL17/pgvector + Redis7 + Neo4j migration/evidence/erasure/restart gates and non-root Docker readiness/auth/restart/persistence/erasure passed. No image was deployed or published to a registry. Fixed clean install sqlalchemy[asyncio], PC type resolution against its own SDKs, FFmpeg CI prerequisite, and FastAPI0.150 lazy router ownership via public iter_route_contexts with old-version fallback; latest deps/real Postgres also passed locally. Legacy platform send/broadcast no longer records unconfirmed sends as success. Read docs/deployment.md and docs/platform-conversations.md. The isolated CI snapshot preserves the original master checkout/index and all existing working files. Local .codex/config.toml contains a secret already present in remote history; it is excluded from the published snapshot and ignored, but preserved locally. The owner has been told to rotate that credential; never print it or rewrite history automatically. 3D stack was researched only, no 3D dependency or renderer implemented; existing avatar_runtime remains the accepted 2D/audio timeline. Preserve native O2 1.2.1.1 and SQLite lifecycle. No new subagents. Production QA state is in ignored output/qa/production-context.json.

Latest V2.26: 35/38 accepted (92%). Platform implementation is in place; actual social-account validation is deferred by the user. The user also explicitly deferred 3D development until the other work is complete and the technical approach is discussed and confirmed. Do not implement 8.6 or install a 3D stack now. Continue 6.3 actual remote CI/container verification. Read apps/backend/docs/platform-conversations.md. Opt-in host-private config, exact actor/conversation/thread owner bindings, persistent inbox/cursors and non-replaying delivery receipts, Telegram polling, discord.py 2.7.1 Gateway, QQ signed loopback callbacks, bounded text sends, revocation, private/public separation and SQL erasure/export are implemented. Old tokens alone never enable receivers. Unknown sends and interrupted model/tool work never replay. Minimal hashed binding revocations survive erasure; new permission needs a reviewed new binding ID. QQ callback shares the host process and user barrier on a separate loopback port, never a public exemption in the main API. Actual local Discord HTTP/WS exposed and fixed SDK READY-task cleanup; callback listener and SQL lifecycle tests pass. Backend836 (55.22s, strict thread and unraisable warnings), Web86, both builds and6 import contracts pass; clean wheel includes all platform code/extras. No actual external platform messages sent. Public GitHub repository access is available through the connector, while local Docker/WSL are unavailable. NVIDIA RTX4060 8GiB/driver610.88 was detected, but 3D is explicitly on hold. Preserve native O2 1.2.1.1, SQLite lifecycle and all existing changes. No new subagents; private production QA services remain running and their credentials must never be printed.

Latest V2.25: 2.3 accepted,35/38 (92%); continue6.2 platforms,6.3 actualDocker/remoteCI and8.6 3D. Read docs/neo4j-ownership.md. Immutable per-SQL-memory Evidence/Fact projections and user-scoped entity identifiers replace mutable merged pipeline facts. Recall retains SQL source IDs through final revalidation; deleted/faded/legacy-unattributed/foreign facts cannot restore reply/profile summaries. Explicit/precise accepted memory reactivation remains; restore no longer commits inside recall lock or double-counts access. Single-delete SQL receipts, source tombstones, user-loop lock and periodic fair cleanup (4users/32sources/user every5s) work; actual restart and no-restart recovery passed. GraphFence retains only hashed owner key/epochs; server rejects stale writes and repeated old clears preserve fresh-generation facts. Full graph erase removes source tombstones and personal content but retains minimal hashed revocation receipt; never claim secure physical wiping. Actual Postgres/Neo4j/Garnet, conflicting values, faded/restore/delete, legacy/user separation, server fencing and installed-wheel host passed. Real Ark extraction/embedding generated3 facts; single delete no longer leaves facts. Backend778 (42.86s, strict thread warnings), Web85/both builds,6import contracts; targeted Ruff passes. CI graph-evidence gate added but remote not run. Local QA services remain running, metadata output/qa/production-context.json; never print its temp credentials. No new subagents. Preserve current changes. Legacy wrappers remain removed and native O2 stays1.2.1.1. Next platform audit found Telegram send-only HTML, Discord webhook placeholder ID, no QQ receiver; gateway README missing, SessionManager is in-memory and shares user session across channels. Implement explicit host-owned identity/target bindings and opt-in receive/reply; old tokens alone MUST NOT start new receiving or message real accounts. Real external messaging needs explicit test-target authorization; no accounts have been provided. Git origin exists on github.com; Docker/WSL were unavailable, VC tools/dotnet available.

Latest V2.24: still34/38 (89%), continue all remaining work; 2.3 is NOT accepted yet. Read apps/backend/docs/neo4j-ownership.md. Actual private Neo4j5.26.32/Temurin21, reviewed shared-node migration, nested/user isolation, depth1/2, host export/erasure retry and new-process memory-clear recovery passed. Real Ark extraction/embedding produced3 graph facts and fused recall; all-memory clear now removes graph. IMPORTANT: actual single-memory deletion still leaves external graph facts (output/qa/graph-pipeline-live-result.json); next implement immutable per-memory graph provenance, SQL-evidence-filtered recall and durable single-delete cleanup without deleting other memories/users. Current graph_lifecycle uses loop/user mutex + SQL memory epochs and memory_graph_cleanup receipts; startup retries at most4. Do not claim distributed fencing or unbounded/fair background recovery. Legacy ambiguous data requires per-user review and private archive; never guess. Connection diagnostics now exclude userinfo/path/query; disposable QA app credential rotated and matching logs sanitized. Backend773 (46.04s, strict thread warnings), Web83/both builds, 6import contracts, clean-wheel actual host/ASR/memory/catalog passed. CI graph service/gate added but not run remotely. Owned private PG/Garnet/Neo services remain running for continuing integration; metadata output/qa/production-context.json, credentials only in its temp folder. QA8044/5197 remain closed. Next after2.3: platforms6.2, actualDocker/CI6.3, 3D8.6; goal stays active.

Latest V2.23: 2.1 production SQL accepted, 34/38 (89%); continue remaining four items. Read apps/backend/docs/production-storage.md. Actual private PostgreSQL17.11/pgvector0.8.7 with non-superuser app passed two-process host restart, JSON tags, invalid-write rollback, raw/digest continuity, concurrent replay-safe persona, ownership, graph/export/erase and stale-write guards. Real Ark1024 embedding, three-turn compression and post-restart cross-session recall passed. Cache was actual official Garnet v2.2.3, not Redis7 verification. Never restore destructive embedding-column drops or swallow extension startup errors; new HNSW index, old indexes untouched. Legacy migration is available in wheels via python -m memory_system.postgres_schema (default report, --apply lossless transaction). Invalid vectors roll back and different fixed dimensions refuse; legacy users.user_id participates in privacy. Backend765 (40.47s, strict thread warnings), storage/persona/privacy133 (4.52s), import contracts6; Web unchanged from V2.21 (81/both builds). Postgres/Redis7 CI job added but not remotely run. Remaining: Neo4j/ownership migration, platforms, actual Docker/remote CI, 3D. Private QA PG/Garnet temporarily remain running for next graph integration; metadata is in ignored output/qa/production-context.json, credentials only in its temp folder.

Latest V2.22: extra module-boundary work accepted, still 33/38 (87%); continue all remaining work. Backend 765 passed (43.05s, strict thread warnings), 6 import contracts kept; Web unchanged from V2.21 (81, both builds passed). Read apps/backend/docs/module-injection.md. Legacy shared/action_layer sources are archived under ignored output and excluded from wheels; keep the action_layer runtime capability key. MemoryReader is host-injected with SQL ownership checks; legacy HTTP fallback remains. SpeechRecognizer factories live per app, REST per request and cloud/legacy WS per connection, with cancellation-settled cleanup. Native O2 stays 1.2.1.1; TTS HTTP is still a reference-host singleton. WAV duration uses actual readable frames; unknown codecs return 0. Actual isolated upload ASR/SQL/O2 and clean-wheel host/ports passed. AST reverse/SDK/horizontal imports are zero; persona-text baseline differences remain. Remaining five roadmap items: production SQL, Neo4j/ownership migration, platforms, actual Docker/CI, 3D.

Latest V2.21: 8.5 audio transport accepted, 33/38 (87%); continue all remaining work. Backend 758 passed (42.34s, strict thread warnings), Web 81, both builds passed. Read apps/backend/docs/audio-transport.md and packages/audio-transport/README.md. New clients negotiate framed-v1 before microphone capture; old ready falls back to raw, old clients omit the parameter. Keep bounded JSON/audio, monotonic stream IDs and per-direction connection sequences, cancellation-settled serialized sends, stale-stream rejection and fatal-error microphone cleanup. Access middleware must select only public companion.session/device names, never the credential token. Real O2 new/legacy/interrupt-next-turn plus actual browser fake-mic VAD/framing/playback/hangup passed; no real microphone. Protobuf microbenchmark is offline and optional, no runtime dependency or end-to-end latency claim. Clean wheel host/catalog and codec packaging passed. Architecture scanner excludes generated build/dist; reverse host/SDK imports are zero, existing cross-module/hardcoded baselines remain, not green. QA 8044/5197/browser closed. Remaining roadmap items: 2.1 production SQL, 2.3 Neo4j/migration, 6.2 platforms, 6.3 actual Docker/CI, 8.6 3D; extra shim cleanup and ASR Protocol injection remain.

Latest V2.20: administration (6.4) accepted, 32/38 (84%); continue all remaining work. Backend 750 passed (44.58s, strict thread warnings), Web 75, both builds passed. Role-checked settings/status/catalog, failed-read write lockout, secret/stale response cleanup and shared CareSettings are implemented. Bundled catalog installs require separate host enablement, fixed packaged ID/digest and a writable unlinked root; no overwrite, pre-enabled grants, remote packages or HTTP grant editing. Install stays disabled until host authorization; repeated cancellation drains disk workers. Real isolated browser/Ark/TTS/install/refresh/member/390px and host-granted Ark tool invocation passed; clean wheel host/catalog install/call passed. Read apps/backend/docs/administration.md and plugins/README.md. Cross-module user-state regression now lives at core_orchestrator/tests/test_user_state.py with one async host/client/SQL loop. Remaining: production SQL/Neo4j, multiplatform, actual Docker/CI, transport, 3D and extra shim cleanup/ASR injection.

Latest V2.19: 31/38 (82%), continue remaining work. Backend 745 (63.84s, strict thread warnings), desktop tools 16, Web 67, PC actual builder proxy and both builds passed; both npm audits zero. Use Node 24 LTS (system Node 25 is unsupported by Vitest 5). Actual Windows win-unpacked verified custom app://companion origin, isolated profile, Python bridge, Ark chat and matching same-origin VAD WASM with fake microphone, zero page errors. Preserve PC SDK dedupe, packages/web-runtime-assets and dependency overrides. Explicit custom CORS retains app://companion, never generic null. Docker/remote CI, signed installers and other OS remain unverified. Read PC README and backend/docs/deployment.md; continue administration and remaining items.

Latest V2.18: 7.1/5.4 accepted, 31/38 (82%); continue all remaining work, starting dependency audit cleanup and deployment. Read `apps/backend/docs/desktop-execution-boundaries.md`. Desktop bridge has a private ephemeral key/port; optional host grants never come from model/UI, files stay in a dedicated root, links/overwrite/shell rejected, sensitive operations require local confirmation. Device state uses CAS and claimable-before-push ordering; after confirmation recheck cancellation/expiry. Real isolated Electron 44.9.0/Python/file/SQL and actual Windows notification show passed; confirmation API selection was automated. Real reminder SSE and refresh dedupe passed. Backend 742 (58.02s), desktop tools 16, Web 67, both builds passed. Native OS sandbox for arbitrary code, production stores, full installer, other platforms and full dependency remediation are not claimed. QA 8044/5197/Electron closed.

Latest V2.17 supersedes checkpoints below: 7.2/6.5 accepted, 29/38 (76%), continue until all remaining work is complete. Read `apps/backend/docs/content-safety.md` and `apps/backend/docs/memory-visualization.md`. Keep host-injected voice/task review, pre-publication text/TTS gates and bounded unverified native PCM. Rule filtering is not full semantic moderation. SQL graph views preserve owner/evidence boundaries and never reactivate faded data. Backend 729 (58.61s, thread warnings as errors), Web 66, both builds passed. Isolated real Ark/prevention/TTS/O2 and browser graph evidence/filter/erase/390px passed. QA 8044/5197 and graph-qa closed. Next: device sandbox and remaining administration/ecosystem/deployment work.

Latest V2.16: reference-host 7.3 accepted, 27/38 (71%); continue all remaining work. Read `apps/backend/docs/access-and-privacy.md`. Host keys are hashed/private, sessions revocable, data scoped to owners. Erasure cancels/joins owned work, invalidates inherited SQL contexts and persists pending file/device/graph cleanup; never report success while pending or let new writes in. Plugins have neutral shared workers and copy each call context. Browser startup reconciles deletion receipts before showing cached content. Real isolated chat/TTS/native auth/logout and browser switch/export/erase/lost-response passed. Backend 689 (65.63s), Web 63, Web/PC builds passed. Production storage/multi-worker/standalone deployment remains separate; continue CI/deployment and remaining features.

Latest V2.15: 6.1 accepted, 26/38 (68%), continue remaining work. Local plugin inventory is disabled by default; only a private host grant enables code/users/mutations. Read `apps/backend/plugins/README.md`. Worker-owned cleanup, atomic reload, revocation and unknown-result non-replay are mandatory. Backend 666 passed (55.04s), Web 53, Web/PC builds passed; real Ark task API invoked old/new versions in isolated data. Do not mistake plugin support for an untrusted-code sandbox or full authentication.

Latest V2.14 (2026-10-20) supersedes checkpoints below: 5.2/5.3/8.4 accepted, 25/38 (66%). Continue until all remaining applicable work is done; next plugins/ecosystem. Read `docs/avatar-audio-synchronization.md` under backend. Standalone avatar assembly/TS audio clock, actual RMS mouth, stop/interrupt, refresh replay and native O2 metadata verified with isolated data. Native audio must be announced even when sentence text is missing. Full backend 656 passed (55.58s), Web 53 passed, Web/PC builds passed; avatar independence contract kept.

2026-10-20 current checkpoint: user explicitly requested continuing until the whole plan is complete. 5.2 image understanding accepted (23/38, 61%); continue 5.3/8.4. Read `apps/backend/docs/image-understanding.md`. Image originals remain transient; no remote URL fetching, tool execution or derived personal facts on image turns. Regression: `pytest -q shared_runtime/tests/test_image_input.py shared_runtime/tests/test_llm_images.py core_orchestrator/tests/test_image_turns.py`. Full backend 646 passed (52.76s), Web 46 passed, Web/PC builds passed; one additional SQL image-history test added afterwards.

Current execution ledger: repository-root `DEVELOPMENT_EXECUTION.md` (2026-10-19). The user resumed with **继续开发吧**. 5.1 and 8.1/8.2 are accepted (22/38, about 58%); continue with 5.2 image understanding and the remaining applicable work. The overall plan remains incomplete. Realtime context uses host injection; native turns persist after complete text/audio, with ordered writes and per-session read barriers. Read `apps/backend/docs/realtime-conversation-continuity.md` for actual boundaries and live evidence.

V2.10: specialists share the normal/SSE routing entry point; per-user/session ordering includes both paths. `action_executor/task_agent.py` has an injectable bounded planner and persistent receipts; never replay interrupted/unknown mutations. Resume only awaiting_input tasks. MCP uses the official SDK with worker-owned transport scopes and explicit per-server allowed_users. Read `action_executor/README.md` before configuration; local `companion_mcp_config.json` may hold secrets and stays ignored. Regression: `pytest -q action_executor/tests/test_tool_protocol.py action_executor/tests/test_task_agent.py action_executor/tests/test_task_api.py core_orchestrator/tests/test_specialists.py`. MCP tests launch real local stdio and HTTP servers. The reference host is single-process; distributed task leases/session coordination are not implemented.

V2.11 historical checkpoint: 8.1/8.2 accepted, total 21/38 (55%). `voice_layer/streaming_pipeline.py` owns bounded PCM prefetch and source-order output; local concurrency is 1, cloud 2. `core_orchestrator/streaming_voice.py` emits negotiated SSE voice segments, isolates segment failures, and drains child tasks on disconnect. Web/PC play/replay ordered segments and discard late decoding after interruption. Realtime input is capped at 60 seconds; frontend bounds queued playback to 30 seconds, pending decodes to 16, individual frames to 2 MiB. Native Doubao drops old output until the next ASR-ended event. Audio/emotion/avatar aggregation (8.4), full realtime persona integration (5.1), image understanding and other plans remain pending.

V2.11 historical verification: backend 603 passed (49.76s, thread warnings as errors; three existing deprecations), Web 42 passed, Web/PC builds passed. A cancelled SQLite connection attempt is completed/closed and its worker joined before propagating cancellation (`shared_runtime/database/sqlite_lifecycle.py`); the regression exercises real aiosqlite and repeated cancellation. Fixed-text live TTS comparison: 20 pairs/40 successes, median first audio 6.703s → 4.234s (36.8%); real TTS/ASR roundtrip and native realtime interrupt/next-turn passed. QA services on 8024/5194 and browser `streaming-qa` are closed; artifacts stay in ignored `output/playwright/`.

Lite storage defaults to `apps/backend/companion_lite.db`, independent of cwd. Use `COMPANION_LITE_DATABASE_URL` for isolated instances; pytest sets a temporary database automatically. Proactive generation and voice memory persistence are host-injected callbacks composed in `core_orchestrator/runtime_hooks.py`.

V2.7 memory regression: `pytest -q memory_system/tests --ignore=memory_system/tests/test_memory.py core_orchestrator/tests/test_runtime_hooks.py`. SQLite uses WAL; SQL stores conversation history and digests in both modes. Local relation retrieval requires no Neo4j. Automatic maintenance fades memories reversibly, and a clear operation invalidates older background writers. Pytest disables real automatic model compression; validate live providers only with isolated data.

V2.8 persona regression: `pytest -q persona_engine/tests core_orchestrator/tests/test_runtime_hooks.py memory_system/tests/test_dream.py`. SQL atomically stores continuous emotion and relationship per user/turn. Reaction classification precedes generation and has a bounded model timeout with rule fallback. Dream relationship review receives host-supplied turns and never credits unversioned legacy archives again. Pytest disables real reaction model calls; use isolated data for live provider QA.

V2.9: natural replies are opt-in per user, and quiet acknowledgements remain observed without empty assistant bubbles or TTS. Test `core_orchestrator/tests/test_natural_reply.py`, `persona_engine/tests/test_reply_policy.py` and `core_orchestrator/tests/test_routing_quality.py`. Routing evaluation: `python tools/eval_intent_router.py --mode rules` (offline), or `--mode model` (explicit live provider with synthetic cases). Pytest disables real intent calls. Keep cross-module tests in core_orchestrator/tests; business tests must remain independent of the host.

Background memory ingestion is owned by `core_orchestrator/memory_tasks.py`; host shutdown drains it before closing HTTP/SQL resources. SDK test teardown also drains tasks before its event loop closes. Full lifecycle regression adds `-W error::pytest.PytestUnhandledThreadExceptionWarning` to the fast-clean pytest command; V2.9 baseline was 537 passed (43.91 seconds).

This repository uses a **monorepo** for 小暖 Companion AI:

| Area | Path |
|------|------|
| Backend | `apps/backend/` |
| Web | `apps/web/` |
| PC simulator | `apps/pc-client/` |
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

1. Optional: `cd apps/pc-client && pip install httpx && python sim_client.py` (set `XIAONUAN_API_BASE_URL` if needed).
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

## 火山引擎默认配置

聊天/摘要/推理使用火山方舟，记忆使用豆包多模态向量接口（文本输入、1024 维）；ASR、TTS 和实时通话使用豆包语音原生接口。接入说明见 `apps/backend/VOLCENGINE.md`。

- 环境模板：`apps/backend/.env.example`。填写 `COMPANION_ARK_API_KEY`（方舟）与 `COMPANION_VOLC_API_KEY`（豆包语音），也可通过设置页保存。两个服务的 Key 分开配置。
- 实时通话默认 `volc_realtime` / O2.0；没有 Key 时提示配置错误。旧的外部 2D 生成接口仍是占位协议，默认本地动作。
- 接口契约回归（无需真实密钥）：在后端运行 `pytest -q core_orchestrator/tests/test_volcengine.py shared_runtime/tests voice_layer/tests action_executor/action2d/tests`。
- 运行时 JSON 与环境文件包含密钥，应保持 Git 忽略；不要将 API Key 写入文档、测试或日志。


## V2.12 current verification

Backend 624 passed (52.22s, thread warnings as errors), Web 42 passed, Web/PC builds passed. Live isolated synthetic QA verified text agreement recalled by native voice, actual ASR/audio (555002 bytes), SQL persistence after cache invalidation, one relationship commit, and voice facts recalled by subsequent text. Native context is a startup snapshot; reaction classification runs at completed-turn commit. Playback acknowledgement and host tool execution in native calls remain outside this implementation. SQLite worker lifecycle now owns queries and closure as well as connection opening.
