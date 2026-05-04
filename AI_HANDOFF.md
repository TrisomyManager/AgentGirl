# AI 工程交接文档

> 写给接手本工程的 AI（或新开对话的自己）。  
> 更新日期：2026-04-30

---

## 一、项目是什么

**目标产品**：陪伴类 AI 智能体 / 数字生命系统

不是普通聊天机器人，核心差异点：

| 能力维度 | 说明 |
|---|---|
| 稳定人格 + OOC 边界 | 角色不跳戏，有明确的角色扮演边界规则 |
| 长短期记忆 + 用户画像 | 跨会话记忆、关系状态、情感指标 |
| 多模型路由 | 云端 API（GPT/Claude/Gemini）+ 本地模型（Llama/Qwen）可切换 |
| 语音全链路 | ASR → 情感分析 → LLM → TTS → 情绪语音输出 |
| 角色表现层 | Unity/Web/移动端，支持口型、表情、动作、3D骨骼同步 |
| 工具能力 | 文件/代码/表格/搜索，带安全沙箱 |
| 跨设备协同 | 多端注册、心跳、任务下发、状态同步 |
| 可观测性 | Prometheus + Grafana + LangSmith 链路追踪 |

---

## 二、技术底座

工程核心是 **[hermes-agent](hermes-agent/)** —— NousResearch 出品的开源自改进 AI Agent 框架（MIT 协议）。  
我们把它作为底座，在上层叠加陪伴类产品所需的能力。

### hermes-agent 核心文件索引

| 文件/目录 | 作用 |
|---|---|
| [hermes-agent/run_agent.py](hermes-agent/run_agent.py) | `AIAgent` 核心对话循环（~12k LOC） |
| [hermes-agent/model_tools.py](hermes-agent/model_tools.py) | 工具编排，`handle_function_call()` |
| [hermes-agent/cli.py](hermes-agent/cli.py) | 交互式 CLI（`HermesCLI`，~11k LOC） |
| [hermes-agent/hermes_state.py](hermes-agent/hermes_state.py) | SQLite 会话存储（FTS5 搜索） |
| [hermes-agent/agent/](hermes-agent/agent/) | 各模型适配器、记忆、缓存、压缩 |
| [hermes-agent/gateway/](hermes-agent/gateway/) | 消息网关（Telegram/Discord/Slack/API服务器…） |
| [hermes-agent/tools/](hermes-agent/tools/) | 工具实现，含终端后端（local/docker/ssh/modal…） |
| [hermes-agent/plugins/](hermes-agent/plugins/) | 插件系统（记忆提供者、图像生成…） |
| [hermes-agent/cron/](hermes-agent/cron/) | 定时任务调度器 |
| [hermes-agent/environments/](hermes-agent/environments/) | RL 训练环境（Atropos 框架） |

用户配置在 `~/.hermes/config.yaml`，API Key 在 `~/.hermes/.env`。

---

## 三、架构规划（已定稿）

完整架构分 9 层，详见 [陪伴类 AI 智能体 – 完整项目架构与技术选型文档.md](陪伴类%20AI%20智能体%20–%20完整项目架构与技术选型文档.md)。

**分层概览**：

```
客户端层（Flutter/Unity/WebGL）
    ↓
接入网关层（Kong/Traefik + Redis + WebSocket）
    ↓
控制编排层（LangGraph 状态机 + 工具调度 + 跨设备编排）
    ↕
语音动作协同层（ASR→TTS→动作生成→口型同步）
    ↕
记忆系统层（长期: pgvector+Neo4j+Mem0 / 短期: Redis）
    ↓
模型推理层（LiteLLM 网关 → 云端API / 本地LoRA）
    ↓
异步记忆沉淀层（Celery 五阶段流水线）
    ↕
跨设备协同层（RocketMQ/MQTT + 端到端加密）
    ↕
持久化与运维（PostgreSQL + MinIO + Prometheus）
```

**技术选型原则**：60% 开源 + 30% 集成 + 10% 自研（核心壁垒）。

---

## 四、三阶段落地计划

| 阶段 | 周期 | 重点 | 状态 |
|---|---|---|---|
| **阶段一：MVP** | 1-2 个月 | 以 hermes-agent 为底座，实现记忆、对话、基础工具 | 🚧 进行中 |
| **阶段二：体验增强** | 2-3 个月 | 集成 ASR/TTS、动作生成、办公能力 | ⏳ 待启动 |
| **阶段三：生态构建** | 2-3 个月 | 完善跨设备协同、安全防护、运维体系 | ⏳ 待启动 |

---

## 五、当前活跃开发计划（.plans/）

### 5.1 OpenAI 兼容 API 服务器

文件：[hermes-agent/.plans/openai-api-server.md](hermes-agent/.plans/openai-api-server.md)

**动机**：让 hermes-agent 能被 Open WebUI、LobeChat、LibreChat 等主流前端直接对接，无需定制适配器。

**三个阶段**：

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 (MVP) | `gateway/platforms/api_server.py`，非流式响应，Bearer Token 鉴权，`/v1/chat/completions` + `/v1/models` + `/health` | ⏳ 待实现 |
| Phase 2 | SSE 真流式输出，`AIAgent.run_conversation()` 加 `stream_callback` 参数 | ⏳ 待实现 |
| Phase 3 | 工具透传模式、模型 passthrough、并发限制、CORS、用量统计 | ⏳ 待实现 |

**关键设计决策**：
- 采用 Option A（Gateway Platform Adapter），复用网关基础设施，不重复造轮子
- 默认无状态（messages 数组即会话），`X-Session-ID` 头开启持久化会话
- 服务端口默认 `8642`，配置键 `api_server.enabled`

**需要新建/修改的文件**：

| 文件 | 变更 |
|---|---|
| `gateway/platforms/api_server.py` | 新建，~300 行 |
| `gateway/config.py` | 加 `Platform.API_SERVER` 枚举 |
| `gateway/run.py` | 注册新适配器 |
| `tests/gateway/test_api_server.py` | 新建测试 |

### 5.2 流式 LLM 响应支持

文件：[hermes-agent/.plans/streaming-support.md](hermes-agent/.plans/streaming-support.md)

**动机**：用户看到逐 token 生成而不是等待全量响应。

**核心设计**：
- 功能标志控制：`streaming.enabled: true`（默认 off，零风险）
- `stream_callback(text_delta: str)` 注入到 `AIAgent`，平台无关
- 提供者不支持时自动降级，不影响现有路径

**当前状态**：计划文档已写，尚未开始实现。此功能是 API 服务器 Phase 2 的前置依赖。

---

## 六、预算与团队参考

详见 [陪伴类AI智能体_分模块预算与团队执行方案.md](陪伴类AI智能体_分模块预算与团队执行方案.md)

- 核心角色：技术架构师、AI 后端、记忆系统、Unity 客户端、语音多模态、DevOps
- MVP 阶段非人力云成本估算：0.5-2 万/月（服务器+存储+LLM API）
- 全栈完整平台：30 万+/月（规模化后）

---

## 七、接手时的优先动作

1. **先从 `companion-ai` 当前入口验证现状**：进入 `companion-ai/` 后优先运行 `python -m pytest -q` 和 `uvicorn main:app --reload --port 8000`
2. **读懂 `companion-ai` 当前单体入口与状态机**：先看 [companion-ai/main.py](companion-ai/main.py) 和 [companion-ai/core_orchestrator/state_machine.py](companion-ai/core_orchestrator/state_machine.py)
3. **读懂 hermes-agent 核心循环与网关参考实现**：再回看 [run_agent.py](hermes-agent/run_agent.py)、[model_tools.py](hermes-agent/model_tools.py) 以及 `gateway/` 下现有 adapter
4. **优先补 `prompt_engine` 与去硬编码 prompt**：这是 companion-ai 继续推进 MVP 前最值得先收敛的点
5. **再处理 hermes-agent 的 OpenAI 兼容 API 计划**：`.plans/openai-api-server.md` 和 `.plans/streaming-support.md` 仍然有效，但不应覆盖 companion-ai 当前 Phase 0/1 收敛工作

---

## 八、当前已知未解决问题 / 注意事项

- hermes-agent 是 **WSL2/Linux/macOS** 项目，原生 Windows 不支持。本机开发需在 WSL2 中运行。
- `companion-ai` 当前可直接在 Windows + Python 3.11 下运行和测试；Lite Mode 健康检查已通过。
- `ENABLE_TOOL_SEARCH=false` 必须设置，否则 Kimi Code 端点会报 400 错误（详见 `~/.claude/CLAUDE.md`）。
- `.plans/` 目录下的计划文件均为**意图文档**，尚未产生实际代码变更，不要误以为功能已实现。
- hermes-agent 测试套件约 15k 个测试，改动核心路径时务必在本地跑 `scripts/run_tests.sh`。
- `companion-ai` 当前 Python 测试基线为 **93 passed**；如果这条失效，优先检查最近是否改了 Lite Mode、memory pipeline、device registry 或事件模型。
