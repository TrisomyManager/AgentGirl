# AI 工程交接文档

> 写给下一位接手本工程的 AI，或者下一轮对话里的自己。  
> 更新日期：2026-05-05

---

## 1. 先看结论

当前真正活跃、应该优先推进的工程是 **[companion-ai](companion-ai/)**。  
`hermes-agent/` 仍然是重要底座和参考实现，但本轮交接应默认以 `companion-ai` 的代码现状为准，而不是以根目录的历史规划为准。

目前项目所处阶段可以概括为：

- **Phase 1.5：实时语音 MVP 已打通**
- **单体 FastAPI 入口已成为默认开发模式**
- **前端调试能力已明显领先于后端收敛度**
- **记忆系统、Prompt 组装和测试稳定性是下一阶段的主战场**

---

## 2. 当前状态快照

### 已经比较成型的部分

- `companion-ai/main.py`
  - 单体入口可挂载全部 router，适合作为本地开发默认入口。
- `companion-ai/frontend_app/`
  - 已有聊天界面、设置抽屉、记忆库、项目状态面板、实时语音通话面板。
- `companion-ai/voice_layer/`
  - 已打通浏览器端 VAD、AudioWorklet PCM 录音、WebSocket 双向流、边合成边播放、barge-in 打断。
- `companion-ai/shared/`
  - 已有统一 LLM 配置、运行时配置持久化、共享模型与日志基础设施。
  - `LLMClient.generate_stream()` 已就位，OpenAI / Anthropic 双 provider 都支持 token 级流式。
- `companion-ai/core_orchestrator/`
  - LangGraph 状态机 + `POST /orchestrator/turn/stream` SSE 端点已打通，主聊天和实时语音的"流式语义"已经统一。
- `companion-ai/core_orchestrator/project_status.py`
  - 目前是“项目当前实现状态”的最准入口之一，前端状态页直接消费它。

### 还没真正收口的部分

- `action_executor` 真实接入
  - 已经有 5 个内置 handler 和提醒 SSE 推送，但天气 / 日历是 stub，等外部 key 配置；循环 / cron 风格调度尚未实现。
- `action_layer` / `device_coordination`
  - 2D 动作生成 + 设备协同仍是占位。
- 调试台 / Prompt 可视化
  - `state_machine.py` 装配出的最终 system prompt（含 working memory 注入的【当前对话状态】section）尚未在调试台呈现。
- working memory 摘要质量
  - dominant_topic / 用户摘要目前是 bag-of-words 启发式，未来可以替换为 LLM 摘要器。

---

## 3. 现在代码里“真实存在”的能力

### companion-ai

- 运行模式
  - 单体模式：`uvicorn main:app --reload --port 8000`
  - Lite Mode：`COMPANION_LITE_MODE=true`，使用 SQLite + 内存替代，适合无 Docker 环境
- 前端能力
  - 文本聊天
  - 语音输入
  - 实时语音通话
  - Live2D 展示
  - LLM / Voice Provider 运行时切换
  - 项目状态可视化
- 运行时配置
  - `companion_llm_config.json`
  - `companion_voice_config.json`
- 状态接口
  - `/health`
  - `/orchestrator/project_status`
  - `/orchestrator/settings/llm`
  - `/orchestrator/settings/voice`

### hermes-agent

- 仍然适合作为这些方向的参考和复用来源：
  - gateway adapter
  - tools 体系
  - prompt_builder / context_compressor 的设计思路
  - cron / 自动化调度
- 但不要默认认为 hermes-agent 的 `.plans/` 就等于 companion-ai 当前优先级。

---

## 4. 先读哪些文件

如果要在最短时间内恢复上下文，建议按这个顺序：

1. [companion-ai/main.py](D:/DeskTop/AgentGril/companion-ai/main.py)
2. [companion-ai/core_orchestrator/project_status.py](D:/DeskTop/AgentGril/companion-ai/core_orchestrator/project_status.py)
3. [companion-ai/core_orchestrator/api.py](D:/DeskTop/AgentGril/companion-ai/core_orchestrator/api.py)
4. [companion-ai/core_orchestrator/state_machine.py](D:/DeskTop/AgentGril/companion-ai/core_orchestrator/state_machine.py)
5. [companion-ai/frontend_app/src/App.vue](D:/DeskTop/AgentGril/companion-ai/frontend_app/src/App.vue)
6. [companion-ai/frontend_app/src/components/ProjectStatusPanel.vue](D:/DeskTop/AgentGril/companion-ai/frontend_app/src/components/ProjectStatusPanel.vue)
7. [companion-ai/voice_layer/realtime.py](D:/DeskTop/AgentGril/companion-ai/voice_layer/realtime.py)
8. [companion-ai/shared/llm_client.py](D:/DeskTop/AgentGril/companion-ai/shared/llm_client.py)

---

## 5. 本地验证建议

### 最小验证路径

在 `companion-ai/` 目录执行：

```powershell
python -m pytest -q
uvicorn main:app --reload --port 8000
```

前端单独验证：

```powershell
cd frontend_app
npm run build
```

### 2026-05-05 的实际验证结果

- `python -m pytest -q`
  - **125 passed / 0 failed**（streaming 4 + working memory 9 + action_executor 15）
- 修复要点
  - `pyproject.toml` 现在显式声明 `numpy` 依赖，`voice_layer` 不再因
    `ModuleNotFoundError: numpy` 在干净 venv 中整组 collect 失败。
  - `shared/tests/test_prompt_engine.py` 的英文断言已与
    `shared/prompt_engine.py` 的中文 prompt 对齐，2 个长期红测已转绿。
  - `memory_system/tests/test_memory.py` 之前的 SQLite 向量绑定问题在
    上一轮 `memory_system/db.py` / `vector_store.py` 调整后已恢复绿色。
- 仍需注意：`voice_layer` 的真实音频集成（`ffmpeg`、`faster-whisper`、`piper-tts`
  模型下载）在 CI / 干净机器上仍是潜在阻塞点；当前测试通过 monkeypatch
  避开了这条硬依赖路径。

---

## 6. 下一步推荐动作

> 已收口：`companion-ai/.env` 路径固定为包根目录（`shared/config.py` 中 `_COMPANION_ROOT / ".env"`），避免 uvicorn cwd 导致 lite_mode 丢失；`GET /actions/push/poll` + 前端 2.5s 轮询作为 Cloudflare / nginx 缓冲场景下的兜底；SSE 首包 padding 提至 4KB；状态面板「Prompt 调试」可拉取 `GET /orchestrator/debug/system_prompt`；无 ffmpeg 时 3 个 voice_layer 用例自动 skip。

仍建议优先：

1. **远端 Cloudflared 路径上复测** `/actions/push` 与 `/actions/push/poll`（首字节 <2s、ReminderToast 弹出）。
2. **working memory 摘要 LLM 化** —— 当前 dominant_topic 仍是 bag-of-words 启发式。
3. **persona_engine 微服务模式接 SSE** —— 去掉 `state_machine.stream_assistant_response` 中针对该路径的"非流式 fallback"。
4. **action_executor**：天气 / 日历真实 API、cron 风格调度。

---

## 7. 容易踩坑的点

- `hermes-agent` 更偏 WSL2/Linux/macOS 工作流；在这台 Windows 机器上不要默认先从它启动。
- `companion-ai` 才是当前本机最顺手的开发入口。
- 根目录旧文档里很多内容是“长期目标”，不是“今天已经实现”。
- 页面状态展示以 `core_orchestrator/project_status.py` 为准；如果代码实现变化了，优先同步这里，再同步文档。
- 当前仓库是脏工作区：
  - `.gitignore` 已有用户改动
  - `companion-ai/.env.lite` 是未跟踪文件
  - 不要误清理

---

## 8. 一句话交接

这不是一个“从零开始搭骨架”的项目了，而是一个 **实时语音体验先跑出来、现在需要把记忆、提示词和工程稳定性补齐** 的项目。接手时请把注意力放在 `companion-ai`，并优先相信代码与状态接口，而不是旧规划文本。

---

## 9. 本轮待续工作（2026-05-05 中段交接）

> 这一轮 token 用尽前正在做"动作执行器初始闭环"。已经 push 到 `cursor/repo-issue-fixes-29a4` 的代码处于"测试全绿，但远端 lite/CF 路径下端到端 demo 没完全走通"的状态。下一轮接手请按这里的清单收口。

### 已完成（已合入分支）

- `action_executor/` 新模块：
  - `registry.py` —— `ActionRegistry` + `ActionResult` + `register_action` 装饰器。
  - `handlers.py` —— 5 个内置 handler：`get_time` / `get_weather`(stub) / `set_reminder` / `list_reminders` / `cancel_reminder`。`set_reminder` 会解析 "3 分钟后"、"in 5 minutes" 等自然语言延迟。
  - `reminders.py` —— `ReminderORM`（SQLAlchemy 表）+ `RemindersStore`（add / list / due / mark_fired / cancel）+ `ReminderScheduler`（默认 1s 轮询；用 `_tick_once` 在测试中可手动驱动）。
  - `push_bus.py` —— 进程内 pub/sub `ProactivePushBus`，每个 subscriber 一条 `asyncio.Queue`。
  - `api.py` —— `/actions/list` / `/actions/dispatch` / `/actions/reminders/{user_id}` (GET / POST) / `/actions/reminders/{id}` (DELETE) / `/actions/push` (SSE)。
  - `main.py` —— 微服务模式 lifespan（启动 / 停止 scheduler），同时被 monolithic `companion-ai/main.py` 复用。
- `core_orchestrator/state_machine.py`：
  - 新增 `_try_action_executor(tc, intent)`：当 intent 是 `TOOL_USE` 时按关键字匹配 handler 并 dispatch。
  - 在 `node_generate_response`（非流式）和 `stream_assistant_response`（流式）两条路径里都接入了这个分支：handler 命中后跳过 LLM，直接渲染 handler 返回的文本。流式分支用 `chunk_text_stream` 切片 SSE。
- `core_orchestrator/intent_router.py` 的 `_TOOL_KEYWORDS` 加了「提醒我 / 帮我提醒 / 待办提醒 / 取消提醒 / remind me / set reminder」等。
- `frontend_app/`：
  - `useApi.ts` 新增 `listReminders` / `cancelReminder` / `listActions`。
  - 新建 `composables/useProactivePush.ts`：用 `fetch + ReadableStream + TextDecoder` 解析 `/actions/push` SSE，自动断线重连，对外暴露 `lastReminder` ref。
  - 新建 `components/ReminderToast.vue`：粉色 ⏰ 浮窗，3-4 行内显示提醒文字 + 点 `×` 关闭。
  - `App.vue` 装载 `useProactivePush()` + `<ReminderToast :reminder="lastReminder" @dismiss="...">`。
- `companion-ai/main.py`：把 `action_executor` 加进了 `_ENABLED_MODULES`，挂载 router，按反向顺序卸载 lifespan。
- `pyproject.toml.tool.setuptools.packages.find` 也加上 `action_executor*`。
- `core_orchestrator/project_status.py`：
  - `action_executor` 模块卡片从 PLANNED 10% 升到 IN_PROGRESS 55%，加了 7 条 🆕 key_features。
  - 顶层 `recent_highlights` / `next_focus` / `risks` / `test_snapshot` / `release_notes.items` 全部同步。
  - `architecture_layers["能力层"]` 把 `action_executor` 和 `action_layer` 都列上。
  - `overall_progress=92`、`test_snapshot.passed=125`。
- `action_executor/tests/test_action_executor.py`：15 个用例，**全绿**。覆盖 registry / 内置 handler / reminders store / scheduler 与 push bus / NL 文本解析。
- 文档：`AI_HANDOFF.md` / `PROJECT_PLAN.md` 同步基线 110 → 125 / 0。
- `pytest -q` —— **125 passed, 0 failed**。
- 本地直连后端的 curl 端到端实测：「8 秒后提醒我喝水」→ intent_router 路由到 `tool_use` → `_try_action_executor` 选中 `set_reminder` → 持久化到 `reminders` 表 → 后台 scheduler 触发 → `ProactivePushBus.publish` → `/actions/push` SSE 上看到 `event: reminder_fired`。流程完整。

### 还没收口的两件事

#### 9.1 `/actions/push` 在 Cloudflare 隧道下首字节延迟太长

**症状**：直连本机 `127.0.0.1:8000/actions/push` 一切正常；同样的请求经 Cloudflare Quick Tunnel 转发后，**首字节迟迟不到**（在浏览器 DevTools 探针脚本中等了 15s 也收不到 `event: hello`）。直接结果：浏览器 `useProactivePush` 永远拿不到 `reminder_fired` 事件，前端 `ReminderToast` 不显示。

**已经做了的修补**：在 `action_executor/api.py::push_stream` 里：
- 头先发一个 ~2KB 的 SSE comment padding（`":" + " "*2048 + "\n"`），强制 cloudflared 立刻 flush 第一段。
- 主循环用 `asyncio.wait_for` 包 subscriber 的 `__anext__()`，没事件时每 2s 发一帧 `event: ping\ndata: {}\n\n` 心跳，避免 CF / nginx 在长时间没数据时挤压缓冲。
- 响应头已经有 `Cache-Control: no-cache, no-transform`、`Connection: keep-alive`、`X-Accel-Buffering: no`。

**还没做完**：远端 VM 上重启 backend 之后，**没来得及做完整端到端实测**就让 token 用完了。lite-mode 验证（见 9.2）也撞到下面的问题，所以现在 push_stream 改完之后是**只在测试里被静态调用过，没在真实 cloudflared 路径上走通**。

下一步建议：
1. 用 lite-mode 重启 backend（见 9.2）。
2. `curl -sN https://<cf-tunnel>/actions/push` 看首字节是否 < 2s 到达。
3. 若到达 → 用浏览器探针脚本（在我的对话历史里有完整版本）订阅 `/actions/push` 同时通过 `/orchestrator/turn` 触发 `8 秒后提醒我喝水`，看 `event: reminder_fired` 是否到。
4. 若仍不到 → 继续把 padding 加到 4KB / 把 ping 间隔降到 1s；再不行就考虑用 polling fallback (`GET /actions/push/poll?since=...`) 替换 SSE 那条路径。

#### 9.2 lite-mode 兼容：`reminder_scheduler.tick_failed [Errno 111]`

**症状**：在云端 VM 上 `pkill uvicorn` 后用 tmux 重启时，monolithic 模式 `lite_mode=False` 是默认，所以 `reminders.RemindersStore.list_due()` 试图连 PostgreSQL → Connection refused → scheduler 每秒 spam warning。

**已经做了的修补**：当前的 `companion-ai/main.py` 已经在 lifespan 里调 `init_database_schema()`，shared engine 是按 `settings.lite_mode` 选 SQLite 或 Postgres 的，所以**只要启动时 export `COMPANION_LITE_MODE=true`，scheduler 就会走 SQLite，不会再有 Connection refused**。

**还没做完**：我在最后两轮 restart 时手动 export 了 `COMPANION_LITE_MODE=true` 但 tmux send-keys 似乎没把 env 真正传进 uvicorn 进程，导致还是 lite_mode=False。下一轮接手务必一次性确认：

```bash
tmux -f /exec-daemon/tmux.portal.conf kill-session -t companion-backend 2>/dev/null
tmux -f /exec-daemon/tmux.portal.conf new-session -d -s companion-backend -c /workspace/companion-ai -- bash -l
tmux -f /exec-daemon/tmux.portal.conf send-keys -t companion-backend:0.0 \
  "export COMPANION_LITE_MODE=true COMPANION_MONOLITHIC=true COMPANION_ENABLE_VOICE=false COMPANION_ENABLE_ACTION_2D=false COMPANION_ENABLE_DEVICE_COORDINATION=false COMPANION_ENABLE_MEMORY_PIPELINE=false" C-m
tmux -f /exec-daemon/tmux.portal.conf send-keys -t companion-backend:0.0 \
  "/workspace/companion-ai/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 2>&1 | tee /tmp/backend.log" C-m
sleep 6
grep "lite_mode=" /tmp/backend.log    # 必须看到 lite_mode=True
```

**已补齐的文档/约定（本轮）**：`companion-ai/.env.example` 现已包含上述 Lite Mode 相关变量说明；把该文件复制为同目录下的 `.env`（仓库已 gitignore）即可让 pydantic-settings 在任意启动方式下 pick up，无需依赖 tmux 里 fragile 的 `export` 行。更省事的一键启动仍推荐 `python scripts/start_lite_server.py`（在 import `main` 之前强制 `COMPANION_LITE_MODE=true`）。

### Cloud preview URL（可能已失效）

- 前端：<https://condos-behind-weekend-synthesis.trycloudflare.com>
- 后端：<https://ambient-rent-immigrants-face.trycloudflare.com>

这两个 URL 是上一轮跑的 `cloudflared` quick tunnel，**会随 cloud agent VM 关机而消失**。下一轮接手如果要复用预览，建议：

1. `/opt/tools/cloudflared` 已装好；`/opt/tools/node` 是 Node 20。
2. 重启后用上面 9.2 的命令拉起后端，再 `tmux new-session -d -s cf-backend "cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000 2>&1 | tee /tmp/cf-backend.log"`，从日志里抓 `https://*.trycloudflare.com` URL。
3. 前端类似：`tmux new-session -d -s companion-frontend -c /workspace/companion-ai/frontend_app -- bash -l`，发 `export VITE_API_BASE_URL=<刚才的后端 URL>` + `npm run dev -- --host 127.0.0.1 --port 5173`，再起一条 cloudflared 转 5173。
4. **Vite 5 的 `server.allowedHosts` 必须设**：本地我把 `vite.config.ts` 改成 `allowedHosts: true` 用于云端预览，但这个改动**没有提交**（避免污染本地路径）。下一轮接手如果要再次走 cloudflared，记得手动在 VM 上加上同样一行。

### 仓库当前状态

- 分支：`cursor/repo-issue-fixes-29a4`，已 push 到 `origin`。
- PR：[#2](https://github.com/TrisomyManager/AgentGirl/pull/2)。
- 累计 commit：见 `git log master..HEAD --oneline`。
- 工作树有一些**未提交**的本地状态（详见 PR 描述底部「已知限制」）：
  - `companion-ai/frontend_app/vite.config.ts` 的 `allowedHosts: true`（云端预览专用）。
  - `companion-ai/frontend_app/package-lock.json`（npm install 副产品）。
  - 远端 `companion_lite.db` 已经存了几条 fired/cancelled 测试 reminder（用户应当 ignore，下次本地启动会自己生成新的）。
