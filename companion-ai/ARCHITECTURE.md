# Companion AI — 系统架构设计

## 1. 设计原则

- **模块独立**：每个模块为独立 Python 包，可单独运行、单独测试、单独部署。
- **契约先行**：模块间通信通过 `shared/` 中的 Pydantic 模型和事件类型定义，不直接依赖对方实现。
- **云原生**：全走云 API，本地仅运行编排服务和数据层。
- **事件驱动**：核心模块间通过 Redis Pub/Sub 异步解耦；同步调用通过内部 HTTP API。
- **Hermes 底座复用**：保留 Hermes 网关（gateway/platforms/）和工具系统，通过 `gateway_adapter/` 封装为内部服务。

## 2. 模块划分

| 模块 | 职责 | 部署形态 | 端口 |
|------|------|---------|------|
| `core_orchestrator` | LangGraph 状态机、意图识别、记忆/工具/动作/设备调度 | 主服务 | 8000 |
| `persona_engine` | 结构化人格、情感状态机、关系指标、动态语气生成 | 微服务 | 8001 |
| `memory_system` | 短期缓存、向量检索、知识图谱、五阶段记忆沉淀 | 微服务 | 8002 |
| `voice_layer` | ASR(情感感知)、TTS(情感语音)、语音流管理 | 微服务 | 8003 |
| `action_layer` | 2D 照片驱动、动作路由、唇形-表情同步器 | 微服务 | 8004 |
| `device_coordination` | 设备注册中心、MQTT 消息总线、任务分发 | 微服务 | 8005 |
| `gateway_adapter` | Hermes 网关封装、多平台消息收发、会话同步 | 微服务 | 8006 |
| `frontend_sdk` | 独立 App 通信 SDK（WebSocket + REST） | 库/SDK | — |
| `shared` | Pydantic 模型、事件类型、工具函数、配置 | 共享库 | — |

## 3. 数据流

```
User (App/Telegram/Discord)
  │
  ▼
gateway_adapter ──WebSocket──► core_orchestrator
  │                               │
  │    ┌──────────────────────────┼──────────┐
  │    ▼                          ▼          ▼
  │ persona_engine          memory_system   voice_layer
  │    │                          │          │
  │    └────────────────────┬─────┘          │
  │                         ▼                │
  │                    action_layer ◄────────┘
  │                         │
  │                         ▼
  │              device_coordination
  │                         │
  └─────────────────────────┘
```

## 4. 模块间契约

### 4.1 事件总线 (Redis Pub/Sub)

| Channel | 方向 | 载荷 |
|---------|------|------|
| `companion:turn:start` | gateway → core | `TurnStartEvent` |
| `companion:turn:end` | core → gateway | `TurnEndEvent` |
| `companion:memory:sync` | core → memory | `MemorySyncEvent` |
| `companion:action:generate` | core → action | `ActionGenerateEvent` |
| `companion:voice:synthesize` | core → voice | `VoiceSynthesizeEvent` |
| `companion:persona:update` | core → persona | `PersonaUpdateEvent` |
| `companion:device:command` | core → device | `DeviceCommandEvent` |

### 4.2 内部 HTTP API

| 服务 | 端点 | 说明 |
|------|------|------|
| persona_engine | `POST /persona/get_profile` | 获取当前人格状态 |
| persona_engine | `POST /persona/update_emotion` | 更新情感状态 |
| memory_system | `POST /memory/recall` | 语义检索记忆 |
| memory_system | `POST /memory/store` | 存储对话回合 |
| memory_system | `POST /memory/graph_query` | 知识图谱查询 |
| voice_layer | `POST /voice/transcribe` | 语音转文本 |
| voice_layer | `POST /voice/synthesize` | 文本转语音 |
| action_layer | `POST /action/generate` | 生成动作序列 |
| device_coordination | `POST /device/list` | 列出用户设备 |
| device_coordination | `POST /device/send_command` | 向设备发指令 |
| gateway_adapter | `POST /gateway/send` | 向指定平台发送消息 |
| gateway_adapter | `POST /gateway/broadcast` | 多平台广播 |

## 5. 技术选型

| 层级 | 选型 |
|------|------|
| 编排引擎 | LangGraph + Pydantic AI |
| 意图识别 | LLM-as-intent-router (云端 API) |
| 向量数据库 | pgvector (PostgreSQL) |
| 知识图谱 | Neo4j + LangChain GraphRAG |
| 消息总线 | Redis Pub/Sub + MQTT (跨设备) |
| ASR | Whisper API / Groq / 阿里云 |
| TTS | Fish Audio S2 / ChatTTS API |
| 2D 动作 | 通义万相 wan2.2-animate-move |
| 缓存 | Redis |
| 部署 | Docker Compose (MVP) |
| 监控 | Prometheus + Grafana |

## 6. 与 Hermes 的集成边界

```
Hermes 原始代码 ──► gateway_adapter/ (封装为内部服务)
                 │    - 复用 gateway/platforms/* 多平台适配器
                 │    - 复用 gateway/run.py 会话管理
                 │    - 新增 REST API 层供 core_orchestrator 调用
                 │
                 ──► tools/ (通过 shared/tools/ 暴露为内部工具)
                      - 复用现有 40+ 工具
                      - 新增 companion 专属工具（情感分析、动作触发等）
```

Hermes 的 `agent/` 目录（记忆、提示构建、模型路由）将被 companion-ai 的各模块替代，不再直接调用 Hermes 的回合循环。

## 7. 单角色深度养成设计要点

- **唯一人格文件**：`persona_engine/data/soul.yaml` — 不可切换，随时间演化
- **关系指标**：亲密度(intimacy)、信任度(trust)、情绪波动(emotion_variance) — 持久化在 memory_system
- **记忆沉淀**：五阶段流水线将对话自动归档为「事实」「情感」「事件」「偏好」「关系里程碑」
- **成长感**：persona_engine 定期（每日/每周）生成「关系总结」注入系统提示，让人格感受到关系深化

## 8. 2D 驱动 MVP 范围

- 输入：LLM 输出的 `action_intent` + `emotion_tag`
- 路由：根据意图选择「idle」「talk」「listen」「react_happy」「react_sad」等动作模板
- 生成：调用通义万相 API，输入参考图 + 动作描述 → 输出动画帧序列
- 同步：TTS 音频时长 → 唇形关键帧插值 → 前端按时间轴播放
- 前端：App 内 WebView 渲染序列帧（或 Lottie）
