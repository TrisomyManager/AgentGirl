# Companion AI

基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 底座深度定制的陪伴型 AI 智能体。

## 架构概览

Companion AI 当前同时支持两种运行方式：

- 单体模式：本地开发和 MVP 默认方式，一个 FastAPI 进程挂载全部 router
- 微服务模式：保留各模块独立启动方式，便于后续拆分与压测

逻辑模块仍然保持 7 个服务边界 + 1 个前端 SDK：

| 模块 | 端口 | 职责 |
|------|------|------|
| `core_orchestrator` | 8000 | LangGraph 状态机、意图识别、跨模块调度 |
| `persona_engine` | 8001 | 结构化人格、情感状态机、关系指标 |
| `memory_system` | 8002 | 向量记忆、知识图谱、五阶段记忆沉淀 |
| `voice_layer` | 8003 | ASR(情感感知)、TTS(情感语音) |
| `action_layer` | 8004 | 2D 动作生成、唇形同步 |
| `device_coordination` | 8005 | 设备注册、MQTT 消息总线 |
| `gateway_adapter` | 8006 | 多平台网关适配、App WebSocket |
| `frontend_sdk` | — | TypeScript SDK（独立 App） |

## 快速开始

### 1. 配置环境

```bash
cp .env.example .env
# 编辑 .env 填入你的云 API Key
```

### 2. 启动基础设施（完整模式）

```bash
docker compose up -d postgres neo4j redis mosquitto
```

### 3. 安装依赖（开发模式）

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 4. 启动单体模式（推荐）

```bash
uvicorn main:app --reload --port 8000
```

Lite Mode（无需 Docker，使用 SQLite + 内存替代）：

```bash
# PowerShell
$env:COMPANION_LITE_MODE="true"
uvicorn main:app --reload --port 8000
```

### 5. 启动各服务（微服务模式，可选）

```bash
# 核心编排
uvicorn core_orchestrator.main:app --reload --port 8000

# 人格引擎
uvicorn persona_engine.main:app --reload --port 8001

# 记忆系统
uvicorn memory_system.main:app --reload --port 8002

# 语音层
uvicorn voice_layer.main:app --reload --port 8003

# 动作层
uvicorn action_layer.main:app --reload --port 8004

# 设备协同
uvicorn device_coordination.main:app --reload --port 8005

# 网关适配
uvicorn gateway_adapter.main:app --reload --port 8006
```

### 6. 启动 Celery 工作进程（完整模式）

```bash
celery -A memory_system.pipeline worker --loglevel=info
```

### 7. 前端 Web App（本地预览）

`frontend_app/` 是默认的本地调试 / 预览界面（Vue 3 + Vite）。先确保你本机装好了
Node.js（≥ 18）+ npm，然后：

```bash
cd frontend_app
npm install            # 第一次必须先装依赖
npm run dev            # 默认 http://localhost:5173
```

如果后端不是默认的 `http://127.0.0.1:8000`，可以用环境变量覆盖：

```bash
# PowerShell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"; npm run dev

# bash / zsh
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

或者直接用根目录提供的一键脚本同时拉起后端 + 前端：

```bash
# Windows PowerShell
.\start_mvp.ps1
# Windows cmd
start_mvp.bat
```

> 这两个脚本会自动在 `frontend_app/` 下做一次 `npm install`（仅当
> `node_modules/` 缺失时），然后 `npm run dev`，避免干净 clone 后第二个窗口
> 直接 `npm run dev` 报错。

### 8. 前端 SDK（独立 App 集成时使用）

```bash
cd frontend_sdk
npm install
npm run build
```

## 设计决策

- **全云 API**：LLM、ASR、TTS、动作生成全部走云 API，无需本地 GPU
- **单角色深度养成**：唯一人格文件 `persona_engine/data/soul.yaml`，关系指标随时间演化
- **2D 驱动 MVP**：通义万相生成动作序列，前端序列帧渲染 + 唇形同步
- **事件驱动**：模块间通过 Redis Pub/Sub 解耦，同步调用通过内部 HTTP API

## 当前状态

- 单体入口 `main.py` 已可用，Lite Mode 下 `/health` 可正常返回
- 全量 Python 测试已通过：`97 passed / 0 failed`（2026-05-05）
- 计划文档仍保留中长期目标，但以仓库实际实现为准

## 模块间通信

```
Redis Pub/Sub Channels:
  companion:turn:start      → gateway → core
  companion:turn:end        → core → gateway
  companion:memory:sync     → core → memory
  companion:action:generate → core → action
  companion:voice:synthesize → core → voice
  companion:persona:update  → core → persona
  companion:device:command  → core → device

HTTP API:
  core ↔ persona(8001) ↔ memory(8002) ↔ voice(8003)
       ↔ action(8004) ↔ device(8005) ↔ gateway(8006)
```

## 目录结构

```
companion-ai/
├── shared/              # 共享契约（Pydantic 模型、事件、配置）
├── core_orchestrator/   # 核心编排层
├── persona_engine/      # 人格引擎
├── memory_system/       # 记忆系统
├── voice_layer/         # 语音交互层
├── action_layer/        # 动作生成层
├── device_coordination/ # 跨设备协同
├── gateway_adapter/     # 网关适配层
├── frontend_sdk/        # 前端 SDK（TypeScript）
├── docker-compose.yml   # 完整部署
├── Dockerfile           # 统一镜像
└── pyproject.toml       # 依赖管理
```

## License

MIT
