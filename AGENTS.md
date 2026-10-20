# Development Guide

Latest V2.27: 6.3 accepted after actual GitHub Linux CI and Docker smoke; 36/38 accepted (95%). All currently executable planned functionality is handled. Two explicit user deferrals remain: 6.2 real social-account validation (implementation/local protocol/SDK done, no accounts provided), and 8.6 3D development (discuss and confirm the technical approach after other work, never start automatically). Draft PR10: https://github.com/TrisomyManager/AgentGirl/pull/10; successful run39377276774 at a164ab41a7fa73d24fdb848472850803e245dddb. Linux backend839 (67.24s, strict thread/unraisable warnings), desktop tools16, Web86, both clients tests/audit/builds, 6 import contracts, wheel artifact, actual PostgreSQL17/pgvector + Redis7 + Neo4j migration/evidence/erasure/restart gates and non-root Docker readiness/auth/restart/persistence/erasure passed. No image was deployed or published to a registry. Fixed clean install sqlalchemy[asyncio], PC type resolution against its own SDKs, FFmpeg CI prerequisite, and FastAPI0.150 lazy router ownership via public iter_route_contexts with old-version fallback; latest deps/real Postgres also passed locally. Legacy platform send/broadcast no longer records unconfirmed sends as success. Read docs/deployment.md and docs/platform-conversations.md. The isolated CI snapshot preserves the original master checkout/index and all existing working files. Local .codex/config.toml contains a secret already present in remote history; it is excluded from the published snapshot and ignored, but preserved locally. The owner has been told to rotate that credential; never print it or rewrite history automatically. 3D stack was researched only, no 3D dependency or renderer implemented; existing avatar_runtime remains the accepted 2D/audio timeline. Preserve native O2 1.2.1.1 and SQLite lifecycle. No new subagents. Production QA state is in ignored output/qa/production-context.json.

Latest V2.26: 35/38 accepted (92%). Platform implementation is in place; actual social-account validation is deferred by the user. The user also explicitly deferred 3D development until the other work is complete and the technical approach is discussed and confirmed. Do not implement 8.6 or install a 3D stack now. Continue 6.3 actual remote CI/container verification. Read apps/backend/docs/platform-conversations.md. Opt-in host-private config, exact actor/conversation/thread owner bindings, persistent inbox/cursors and non-replaying delivery receipts, Telegram polling, discord.py 2.7.1 Gateway, QQ signed loopback callbacks, bounded text sends, revocation, private/public separation and SQL erasure/export are implemented. Old tokens alone never enable receivers. Unknown sends and interrupted model/tool work never replay. Minimal hashed binding revocations survive erasure; new permission needs a reviewed new binding ID. QQ callback shares the host process and user barrier on a separate loopback port, never a public exemption in the main API. Actual local Discord HTTP/WS exposed and fixed SDK READY-task cleanup; callback listener and SQL lifecycle tests pass. Backend836 (55.22s, strict thread and unraisable warnings), Web86, both builds and6 import contracts pass; clean wheel includes all platform code/extras. No actual external platform messages sent. Public GitHub repository access is available through the connector, while local Docker/WSL are unavailable. NVIDIA RTX4060 8GiB/driver610.88 was detected, but 3D is explicitly on hold. Preserve native O2 1.2.1.1, SQLite lifecycle and all existing changes. No new subagents; private production QA services remain running and their credentials must never be printed.

Latest V2.25: 2.3 accepted,35/38 (92%); continue6.2 platforms,6.3 actualDocker/remoteCI and8.6 3D. Read docs/neo4j-ownership.md. Immutable per-SQL-memory Evidence/Fact projections and user-scoped entity identifiers replace mutable merged pipeline facts. Recall retains SQL source IDs through final revalidation; deleted/faded/legacy-unattributed/foreign facts cannot restore reply/profile summaries. Explicit/precise accepted memory reactivation remains; restore no longer commits inside recall lock or double-counts access. Single-delete SQL receipts, source tombstones, user-loop lock and periodic fair cleanup (4users/32sources/user every5s) work; actual restart and no-restart recovery passed. GraphFence retains only hashed owner key/epochs; server rejects stale writes and repeated old clears preserve fresh-generation facts. Full graph erase removes source tombstones and personal content but retains minimal hashed revocation receipt; never claim secure physical wiping. Actual Postgres/Neo4j/Garnet, conflicting values, faded/restore/delete, legacy/user separation, server fencing and installed-wheel host passed. Real Ark extraction/embedding generated3 facts; single delete no longer leaves facts. Backend778 (42.86s, strict thread warnings), Web85/both builds,6import contracts; targeted Ruff passes. CI graph-evidence gate added but remote not run. Local QA services remain running, metadata output/qa/production-context.json; never print its temp credentials. No new subagents. Preserve current changes. Legacy wrappers remain removed and native O2 stays1.2.1.1. Next platform audit found Telegram send-only HTML, Discord webhook placeholder ID, no QQ receiver; gateway README missing, SessionManager is in-memory and shares user session across channels. Implement explicit host-owned identity/target bindings and opt-in receive/reply; old tokens alone MUST NOT start new receiving or message real accounts. Real external messaging needs explicit test-target authorization; no accounts have been provided. Git origin exists on github.com; Docker/WSL were unavailable, VC tools/dotnet available.

Latest V2.24: still34/38 (89%), continue all remaining work; 2.3 is NOT accepted yet. Read apps/backend/docs/neo4j-ownership.md. Actual private Neo4j5.26.32/Temurin21, reviewed shared-node migration, nested/user isolation, depth1/2, host export/erasure retry and new-process memory-clear recovery passed. Real Ark extraction/embedding produced3 graph facts and fused recall; all-memory clear now removes graph. IMPORTANT: actual single-memory deletion still leaves external graph facts (output/qa/graph-pipeline-live-result.json); next implement immutable per-memory graph provenance, SQL-evidence-filtered recall and durable single-delete cleanup without deleting other memories/users. Current graph_lifecycle uses loop/user mutex + SQL memory epochs and memory_graph_cleanup receipts; startup retries at most4. Do not claim distributed fencing or unbounded/fair background recovery. Legacy ambiguous data requires per-user review and private archive; never guess. Connection diagnostics now exclude userinfo/path/query; disposable QA app credential rotated and matching logs sanitized. Backend773 (46.04s, strict thread warnings), Web83/both builds, 6import contracts, clean-wheel actual host/ASR/memory/catalog passed. CI graph service/gate added but not run remotely. Owned private PG/Garnet/Neo services remain running for continuing integration; metadata output/qa/production-context.json, credentials only in its temp folder. QA8044/5197 remain closed. Next after2.3: platforms6.2, actualDocker/CI6.3, 3D8.6; goal stays active.

Latest V2.23: 2.1 production SQL accepted, 34/38 (89%); continue remaining four items. Read apps/backend/docs/production-storage.md. Actual private PostgreSQL17.11/pgvector0.8.7 with non-superuser app passed two-process host restart, JSON tags, invalid-write rollback, raw/digest continuity, concurrent replay-safe persona, ownership, graph/export/erase and stale-write guards. Real Ark1024 embedding, three-turn compression and post-restart cross-session recall passed. Cache was actual official Garnet v2.2.3, not Redis7 verification. Never restore destructive embedding-column drops or swallow extension startup errors; new HNSW index, old indexes untouched. Legacy migration is available in wheels via python -m memory_system.postgres_schema (default report, --apply lossless transaction). Invalid vectors roll back and different fixed dimensions refuse; legacy users.user_id participates in privacy. Backend765 (40.47s, strict thread warnings), storage/persona/privacy133 (4.52s), import contracts6; Web unchanged from V2.21 (81/both builds). Postgres/Redis7 CI job added but not remotely run. Remaining: Neo4j/ownership migration, platforms, actual Docker/remote CI, 3D. Private QA PG/Garnet temporarily remain running for next graph integration; metadata is in ignored output/qa/production-context.json, credentials only in its temp folder.

Latest V2.22: extra module-boundary work accepted, still 33/38 (87%); continue all remaining work. Backend 765 passed (43.05s, strict thread warnings), 6 import contracts kept; Web unchanged from V2.21 (81, both builds passed). Read apps/backend/docs/module-injection.md. Legacy shared/action_layer sources are archived under ignored output and excluded from wheels; keep the action_layer runtime capability key. MemoryReader is host-injected with SQL ownership checks; legacy HTTP fallback remains. SpeechRecognizer factories live per app, REST per request and cloud/legacy WS per connection, with cancellation-settled cleanup. Native O2 stays 1.2.1.1; TTS HTTP is still a reference-host singleton. WAV duration uses actual readable frames; unknown codecs return 0. Actual isolated upload ASR/SQL/O2 and clean-wheel host/ports passed. AST reverse/SDK/horizontal imports are zero; persona-text baseline differences remain. Remaining five roadmap items: production SQL, Neo4j/ownership migration, platforms, actual Docker/CI, 3D.

Latest V2.21: 8.5 audio transport accepted, 33/38 (87%); continue all remaining work. Backend 758 passed (42.34s, strict thread warnings), Web 81, both builds passed. Read apps/backend/docs/audio-transport.md and packages/audio-transport/README.md. New clients negotiate framed-v1 before microphone capture; old ready falls back to raw, old clients omit the parameter. Keep bounded JSON/audio, monotonic stream IDs and per-direction connection sequences, cancellation-settled serialized sends, stale-stream rejection and fatal-error microphone cleanup. Access middleware must select only public companion.session/device names, never the credential token. Real O2 new/legacy/interrupt-next-turn plus actual browser fake-mic VAD/framing/playback/hangup passed; no real microphone. Protobuf microbenchmark is offline and optional, no runtime dependency or end-to-end latency claim. Clean wheel host/catalog and codec packaging passed. Architecture scanner excludes generated build/dist; reverse host/SDK imports are zero, existing cross-module/hardcoded baselines remain, not green. QA 8044/5197/browser closed. Remaining roadmap items: 2.1 production SQL, 2.3 Neo4j/migration, 6.2 platforms, 6.3 actual Docker/CI, 8.6 3D; extra shim cleanup and ASR Protocol injection remain.

Latest V2.20: administration (6.4) accepted, 32/38 (84%); continue all remaining work. Backend 750 passed (44.58s, strict thread warnings), Web 75, both builds passed. Role-checked settings/status/catalog, failed-read write lockout, secret/stale response cleanup and shared CareSettings are implemented. Bundled catalog installs require separate host enablement, fixed packaged ID/digest and a writable unlinked root; no overwrite, pre-enabled grants, remote packages or HTTP grant editing. Install stays disabled until host authorization; repeated cancellation drains disk workers. Real isolated browser/Ark/TTS/install/refresh/member/390px and host-granted Ark tool invocation passed; clean wheel host/catalog install/call passed. Read apps/backend/docs/administration.md and plugins/README.md. Cross-module user-state regression now lives at core_orchestrator/tests/test_user_state.py with one async host/client/SQL loop. Remaining: production SQL/Neo4j, multiplatform, actual Docker/CI, transport, 3D and extra shim cleanup/ASR injection.

Latest V2.19: still 31/38 (82%), continue all remaining work. Backend 745 passed (63.84s, strict thread warnings), desktop tools 16, Web 67, PC actual builder proxy regression and both builds passed; npm audit is zero for both clients. Use Node 24 LTS, not system Node 25 (unsupported by Vitest 5). Real Windows win-unpacked verified app://companion origin, packaged Python bridge, isolated profile, Ark chat and matching local VAD WASM with fake microphone; zero page errors. Preserve PC SDK dedupe and packages/web-runtime-assets, private custom-origin handling, gh-pages/global-agent overrides. Custom CORS must explicitly retain app://companion, never generic null. Signed installers, Docker/remote CI and other OS remain unverified; 6.3 is in progress. Read apps/pc-client/README.md and apps/backend/docs/deployment.md.

Latest V2.18 supersedes checkpoints below: 7.1 desktop built-in execution boundaries and 5.4 Windows native notifications accepted, 31/38 (82%); continue all remaining work. Read `apps/backend/docs/desktop-execution-boundaries.md`. Preserve private random-port desktop bridge, host-only capability/root grants, per-call confirmation, link/overwrite rejection and no shell execution. Command stores must implement atomic transition; publish claimable state before push, recheck cancellation after confirmation, never replay unknown actions. Real isolated Electron 44.9.0/Python/SQL, file roundtrip, remote cancel and actual OS notification show passed; native confirmation choices were automated, not manually reviewed. Real reminder SSE → Windows and refresh dedupe passed. Backend 742 (58.02s, strict thread warnings), desktop tools 16, Web 67, both builds passed. Frontend/build dependency audit cleanup and remaining production/multiplatform/admin/deployment/protocol/3D work continue. QA 8044/5197 and Electron closed.

Latest V2.17 (2026-10-20): 7.2 content checks and 6.5 memory network accepted, 29/38 (76%); continue all remaining work. Read `apps/backend/docs/content-safety.md` and `apps/backend/docs/memory-visualization.md`. Ordinary/SSE/tool/task/TTS outputs are checked before publication; blocked input never invokes tools. Native PCM without checkable text is bounded/withheld; replacements use separate TTS. Rules are limited, not a full semantic moderation guarantee. Graph views use user-owned SQL evidence, do not reactivate faded memories, and discard stale account/deletion responses. Backend 729 passed (58.61s, thread warnings as errors), Web 66, Web/PC builds passed. Actual isolated Ark/TTS/O2 and browser graph selection/filter/erase/390px passed. Next: device sandbox and remaining administration/ecosystem/deployment work. Earlier checkpoints below are historical.

## Current development state (2026-10-20)

Latest V2.16: 7.3 accepted for the default single-process reference host, 27/38 (71%); continue remaining work. Read `apps/backend/docs/access-and-privacy.md`. Local-only default or private hashed host keys, revocable sessions, per-user ownership, bounded export and durable erasure receipts are implemented. Erasure joins/cancels active user work and invalidates inherited contexts; pending external cleanup blocks new content even after restart. Keep `shared_runtime/user_lifecycle.py`, SQL guards, SQLite worker draining and plugin per-call context ownership. Never log credentials. Real isolated chat/TTS/native auth, logout closure, browser account switching/export/erase/lost-response refresh passed. Backend 689 passed (65.63s, thread warnings as errors), Web 63, Web/PC builds passed. Production storage and multi-worker validation remain separate. Next: deployment/CI and remaining roadmap.

Latest V2.15: 6.1 local plugin discovery/hot reload accepted, 26/38 (68%); continue all remaining work. `action_executor/plugins.py` runs only host-approved code/users, with worker-owned setup/cleanup, atomic reload, revocation and no replay of uncertain mutations. Read `apps/backend/plugins/README.md`. Config is host-only and Git-ignored; never log it. Actual Ark task API called pre/post-reload versions successfully. Backend 666 passed (55.04s, thread warnings as errors); Web 53 and Web/PC builds passed. Plugin regression: `pytest -q action_executor/tests/test_plugins.py action_executor/tests/test_tool_protocol.py action_executor/tests/test_task_agent.py`.

The user requested **继续，直到计划全部完成** on 2026-10-20. Continue all remaining work; do not pause after an iteration. 5.2/5.3/8.4 accepted (25/38, 66%); continue plugins/ecosystem and remaining validation. Read `apps/backend/docs/image-understanding.md` and `apps/backend/docs/avatar-audio-synchronization.md`. Pure `avatar_runtime` assembly and `packages/avatar-runtime` audio clock are independent of the host and renderer. Native O2 must announce actual audio even without vendor sentence text. Latest backend 656 passed, Web 53 passed, Web/PC builds passed; avatar independence contract kept. Preserve SQLite lifecycle draining.

Streaming speech regression: `pytest -q core_orchestrator/tests/test_streaming_voice.py voice_layer/tests/test_streaming_pipeline.py voice_layer/tests/test_realtime_providers.py shared_runtime/tests/test_sqlite_lifecycle.py`. The full Lite regression adds `-W error::pytest.PytestUnhandledThreadExceptionWarning`; latest result: 666 passed, Web 53 passed, Web/PC builds passed. SQLite creation/query/close must finish their worker operations before cancellation propagates; do not remove the lifecycle connector or host-owned connection drain.

V2.12 continuity regression: `pytest -q core_orchestrator/tests/test_voice_context.py voice_layer/tests/test_conversation_context.py voice_layer/tests/test_realtime_memory_sync.py memory_system/tests/test_clear_inflight.py shared_runtime/tests/test_sqlite_lifecycle.py`. Context preparation and completed voice writes are host-injected; ordinary/SSE and chained voice readers wait for earlier completed writes in the same user/session. Native speech uses a startup snapshot and classifies the actual transcript at commit; it does not run host tools. Background SQL memory extraction captures an epoch before queueing and validates it atomically on insert.

SSE clients opt in with `supports_segmented_voice=true` and consume `voice_segment`, `voice_segment_error`, `voice_done`; old clients retain whole-response speech. Default native Doubao realtime stays `volc_realtime`/O2. Live tests must use an isolated database. See `apps/backend/docs/streaming-tts-pipeline-design.md` for the actual implementation and validation limits.

- V2.10 工具/任务回归：后端运行 `pytest -q action_executor/tests/test_tool_protocol.py action_executor/tests/test_task_agent.py action_executor/tests/test_task_api.py core_orchestrator/tests/test_specialists.py`。官方 MCP 测试使用本地 stdio/HTTP 服务，无需外部密钥。
- 语音管线回归：`pytest -q voice_layer/tests --ignore=voice_layer/tests/test_voice.py shared_runtime/tests/test_text_segmenter.py`。本地 TTS 用有界线程队列和停止标志；取消必须关闭迭代器，禁止重新引入无人等待的 run_coroutine_threadsafe 投递。8.1/8.2 已完成 SSE/预合成、前端播放与真实音频验证；8.4 音频/表情同步另行保留。
- MCP 连接由宿主的 `COMPANION_MCP_CONFIG_FILE` 配置，`companion_mcp_config.json` 保持 Git 忽略；不要记录其命令环境、认证头或密钥。任务中断不自动重放；仅 awaiting_input 状态可通过补充信息继续，详细状态名称和入口见 `apps/backend/action_executor/README.md`。

## 当前持续开发任务（2026-10-19）

- 最终目标与逐项验收见根目录 `DEVELOPMENT_EXECUTION.md`。用户已授权持续实现全部适用计划，勿把阶段完成等同于整体完成。
- Lite 数据库默认固定到 `apps/backend/companion_lite.db`；可用 `COMPANION_LITE_DATABASE_URL` 指定隔离实例。pytest 自动使用临时数据库，不读写本地应用数据。
- 主动陪伴通过宿主注入生成器、记忆查询和投递观察器；实时语音通过注入的回调写入记忆。参考集成由 `core_orchestrator/runtime_hooks.py` 组装，业务模块不得反向导入编排器。
- 新增核心回归：后端 `pytest -q action_executor/tests memory_system/tests/test_working_memory.py memory_system/tests/test_session_continuity.py`；前端 `npm test` / `npm run build`；PC `npm run build`。
- V2.7 记忆回归：`pytest -q memory_system/tests --ignore=memory_system/tests/test_memory.py core_orchestrator/tests/test_runtime_hooks.py`。SQLite 默认 WAL；对话原文与摘要均以 SQL 为主存，自动维护使用可恢复淡化，主动清空会使旧后台写入失效。
- 本地图索引无需 Neo4j；日总结的时区与画像更新由宿主回调注入。pytest 禁用真实自动压缩调用，真实服务验证须使用隔离用户与数据库。

This repository uses a **monorepo layout** for the 小暖 Companion AI product:

| Area | Path | Role |
|------|------|------|
| Backend | `apps/backend/` | FastAPI monolith + Python modules (`main.py`, `pyproject.toml`) |
| Web | `apps/web/` | Vue 3 + Vite reference UI |
| PC sim | `apps/pc-client/` | Device gateway simulator (HTTP polling) |
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

Persona regression: `pytest -q persona_engine/tests core_orchestrator/tests/test_runtime_hooks.py memory_system/tests/test_dream.py`. Emotion and relationship use SQL atomically per user/turn; standalone transient engines require explicit storage injection for restart continuity. Classification model/timeouts use `COMPANION_REACTION_*`. Dream relationship review is host-injected; never import persona internals from memory_system.

Conversation/routing regression: `pytest -q persona_engine/tests/test_reply_policy.py core_orchestrator/tests/test_natural_reply.py core_orchestrator/tests/test_routing_quality.py action_executor/tests/test_reminder_language.py`. `python tools/eval_intent_router.py --mode rules` is offline; `--mode model` explicitly evaluates the configured provider with synthetic cases. Pytest disables real intent calls; provider contract tests must explicitly enable their mock setup. Cross-module tests belong in the reference host, not business-module test folders.

### Gotchas

- `COMPANION_LITE_MODE=true` disables Docker dependencies and uses SQLite + in-memory alternatives. `device_coordination` stays enabled; smoke with `apps/pc-client/sim_client.py` (requires `httpx`) or `integration/scripts/smoke-device-flow.ps1` on Windows.
- Internal HTTP clients use `COMPANION_SELF_BASE_URL` when set; otherwise `http://127.0.0.1:{COMPANION_SERVICE_PORT}` (default `8000`).
- Orchestrator conversation endpoints need an LLM API key; health/persona/memory endpoints work without one.
- **Device Gateway** is a backend capability; the PC folder is only a simulator client.

### Web (`apps/web`)

```bash
cd apps/web
npm install
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

### Integration

See [`integration/README.md`](integration/README.md).

## 火山引擎默认配置

聊天/摘要/推理使用火山方舟，记忆使用豆包多模态向量接口（文本输入、1024 维）；ASR、TTS 和实时通话使用豆包语音原生接口。接入说明见 `apps/backend/VOLCENGINE.md`。

- 环境模板：`apps/backend/.env.example`。填写 `COMPANION_ARK_API_KEY`（方舟）与 `COMPANION_VOLC_API_KEY`（豆包语音），也可通过设置页保存。两个服务的 Key 分开配置。
- 实时通话默认 `volc_realtime` / O2.0；没有 Key 时提示配置错误。旧的外部 2D 生成接口仍是占位协议，默认本地动作。
- 接口契约回归（无需真实密钥）：在后端运行 `pytest -q core_orchestrator/tests/test_volcengine.py shared_runtime/tests voice_layer/tests action_executor/action2d/tests`。
- 运行时 JSON 与环境文件包含密钥，应保持 Git 忽略；不要将 API Key 写入文档、测试或日志。
