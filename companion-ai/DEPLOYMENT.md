# Companion AI — 部署指南

本文档将系统拆分为「本地开发包」与「服务端部署包」两部分，解决无 Docker 环境的本地运行需求。

---

## 1. 架构拆分总览

| 模块 | 本地可运行 | 服务端必需 | 说明 |
|------|-----------|-----------|------|
| `core_orchestrator` | ✅ Lite Mode | ✅ | LangGraph 编排核心；本地用内存 EventBus |
| `persona_engine` | ✅ Lite Mode | ✅ | 人格引擎；本地跳过 Redis/Postgres |
| `memory_system` | ✅ Lite Mode | ✅ | 记忆系统；本地用 SQLite 替代 PostgreSQL |
| `voice_layer` | ✅ 原生 | ✅ | ASR/TTS；纯云 API，无外部依赖 |
| `action_layer` | ✅ 原生 | ✅ | 2D 动作；纯云 API，无外部依赖 |
| `device_coordination` | ❌ (单机不需要) | ✅ | 跨设备 MQTT；本地直接禁用 |
| `gateway_adapter` | ❌ (直连核心) | ✅ | 多平台网关；本地 App 直连 core_orchestrator |
| `frontend_sdk` | ✅ 原生 | — | 独立 App SDK |

**本地最小启动集合（5 个服务）：**
- `core_orchestrator`  `:8000`
- `persona_engine`     `:8001`
- `memory_system`      `:8002`
- `voice_layer`        `:8003`
- `action_layer`       `:8004`

**服务端完整集合（7 个服务 + 数据层）：**
- 上述 5 个 + `device_coordination` `:8005` + `gateway_adapter` `:8006`
- PostgreSQL + pgvector, Neo4j, Redis, MQTT (mosquitto)

---

## 2. 本地开发部署（Windows / macOS / Linux，无 Docker）

### 2.1 环境要求

- Python **3.11+**
- 至少 **4GB** 空闲内存
- 云 API Key（OpenAI 或 Anthropic，至少一个）

### 2.2 安装步骤

```powershell
# 1. 进入项目目录
cd companion-ai

# 2. 创建虚拟环境（推荐）
python -m venv .venv
.\.venv\Scripts\activate        # Windows PowerShell
# source .venv/bin/activate     # macOS / Linux

# 3. 安装项目依赖
pip install -e ".[dev]"

# 4. 安装 SQLite 异步驱动（本地必需）
pip install aiosqlite

# 5. 复制本地环境模板
copy .env.lite .env            # Windows
# cp .env.lite .env           # macOS / Linux

# 6. 编辑 .env，填入你的 API Key
notepad .env                   # Windows
# code .env                   # VS Code
```

**必须修改的配置项：**
```ini
COMPANION_OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
# 如果使用 Anthropic：
# COMPANION_ANTHROPIC_API_KEY=sk-ant-xxxxxxxx

# 语音与动作 API（可选，不填则对应功能返回错误）
COMPANION_TTS_API_KEY=your-tts-key
COMPANION_WHISPER_API_KEY=your-whisper-key
COMPANION_ACTION_API_KEY=your-action-key
```

### 2.3 一键启动

**方式 A：双击运行（Windows）**
```
双击 scripts\run_local.bat
```

**方式 B：PowerShell（支持停止/安装）**
```powershell
# 首次安装依赖
.\scripts\run_local.ps1 -Install

# 启动全部服务（5 个独立窗口）
.\scripts\run_local.ps1

# 停止全部服务
.\scripts\run_local.ps1 -Stop
```

**方式 C：手动逐个启动（调试用）**
```powershell
# 开 5 个终端窗口，分别执行：
uvicorn core_orchestrator.main:app --host 127.0.0.1 --port 8000 --reload
uvicorn persona_engine.main:app    --host 127.0.0.1 --port 8001 --reload
uvicorn memory_system.main:app     --host 127.0.0.1 --port 8002 --reload
uvicorn voice_layer.main:app       --host 127.0.0.1 --port 8003 --reload
uvicorn action_layer.main:app      --host 127.0.0.1 --port 8004 --reload
```

### 2.4 验证启动

打开浏览器访问：
- http://127.0.0.1:8000/docs — Core Orchestrator API
- http://127.0.0.1:8001/docs — Persona Engine API
- http://127.0.0.1:8002/docs — Memory System API
- http://127.0.0.1:8003/docs — Voice Layer API
- http://127.0.0.1:8004/docs — Action Layer API

### 2.5 Lite Mode 技术细节

| 组件 | 生产环境 | Lite Mode 替代方案 |
|------|---------|-------------------|
| Redis Pub/Sub | `redis:6379` | 内存 `asyncio.Queue` + 直接回调 |
| 短期记忆缓存 | Redis LRU | 内存 `dict` |
| 长期记忆数据库 | PostgreSQL + pgvector | SQLite (`companion_lite.db`) |
| 向量检索 | pgvector cosine similarity | 全表扫描（数据量 < 1K 可接受） |
| 知识图谱 | Neo4j | **禁用**（`enable_knowledge_graph=false`） |
| 跨设备消息 | MQTT | **禁用**（单机不需要） |
| Celery 任务队列 | Redis + Celery Worker | **禁用**（同步执行或跳过） |

---

## 3. 服务端部署（Docker Compose）

### 3.1 环境要求

- Docker Engine 24.0+
- Docker Compose v2+
- 至少 **8GB** 内存（Neo4j + PostgreSQL 较占资源）

### 3.2 安装步骤

```bash
# 1. 进入项目目录
cd companion-ai

# 2. 创建生产环境配置
cp .env.example .env   # 如没有，可基于 .env.lite 修改
# 编辑 .env，确保以下配置正确：
#   COMPANION_LITE_MODE=false
#   OPENAI_API_KEY=sk-xxx
#   TTS_API_KEY=xxx
#   WHISPER_API_KEY=xxx

# 3. 启动数据层 + 全部服务
docker compose up -d

# 4. 查看日志
docker compose logs -f core_orchestrator

# 5. 停止全部服务
docker compose down
```

### 3.3 服务端口映射

| 服务 | 容器内端口 | 宿主机端口 |
|------|-----------|-----------|
| core_orchestrator | 8000 | 8000 |
| persona_engine | 8001 | 8001 |
| memory_system | 8002 | 8002 |
| voice_layer | 8003 | 8003 |
| action_layer | 8004 | 8004 |
| device_coordination | 8005 | 8005 |
| gateway_adapter | 8006 | 8006 |
| PostgreSQL + pgvector | 5432 | 5432 |
| Neo4j Bolt | 7687 | 7687 |
| Neo4j HTTP | 7474 | 7474 |
| Redis | 6379 | 6379 |
| MQTT | 1883 | 1883 |

### 3.4 仅启动数据层（开发调试用）

```bash
docker compose up -d postgres neo4j redis mosquitto
```

然后可以在本地以 `COMPANION_LITE_MODE=false` 启动各个 Python 服务，连接本地 Docker 数据层。

---

## 4. 前端 App 集成方式

### 4.1 本地开发模式（推荐）

前端 App **直接调用** `core_orchestrator` 的 REST API，跳过 `gateway_adapter`：

```typescript
// 直接发送用户消息
const res = await fetch('http://127.0.0.1:8000/orchestrator/turn', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    session_id: 'sess_001',
    user: { user_id: 'u001', display_name: '小明' },
    user_message: '你好呀',
    platform: 'app',
  }),
});
const data = await res.json();
console.log(data.assistant_message);
```

### 4.2 生产模式（多平台）

前端通过 `gateway_adapter` 的 WebSocket 接入，由网关统一分发到核心编排器：

```typescript
const ws = new WebSocket('ws://your-server:8006/gateway/ws/u001');
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  renderMessage(msg.content);
  playVoice(msg.voice_url);
  playAction(msg.action_sequence);
};
```

---

## 5. 环境变量完整参考

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `COMPANION_LITE_MODE` | `false` | **核心开关**：`true` 启用本地无 Docker 模式 |
| `COMPANION_OPENAI_API_KEY` | — | OpenAI API Key |
| `COMPANION_ANTHROPIC_API_KEY` | — | Anthropic API Key |
| `COMPANION_DEFAULT_LLM_MODEL` | `gpt-4o` | 默认对话模型 |
| `COMPANION_TTS_PROVIDER` | `fish_audio` | TTS 供应商 |
| `COMPANION_TTS_API_KEY` | — | TTS API Key |
| `COMPANION_WHISPER_API_KEY` | — | ASR (Whisper) API Key |
| `COMPANION_ACTION_API_KEY` | — | 2D 动作生成 API Key |
| `COMPANION_ENABLE_VOICE` | `true` | 是否启用语音功能 |
| `COMPANION_ENABLE_ACTION_2D` | `true` | 是否启用 2D 动作 |
| `COMPANION_ENABLE_KNOWLEDGE_GRAPH` | `true` | 是否启用 Neo4j 知识图谱 |
| `COMPANION_ENABLE_DEVICE_COORDINATION` | `true` | 是否启用 MQTT 跨设备 |
| `COMPANION_ENABLE_MEMORY_PIPELINE` | `true` | 是否启用 Celery 异步记忆流水线 |

---

## 6. 常见问题

**Q: 本地启动后 memory_system 报错 `No module named 'aiosqlite'`？**
A: 运行 `pip install aiosqlite`。Lite mode 使用 SQLite 替代 PostgreSQL，需要异步 SQLite 驱动。

**Q: voice_layer 返回 500，`Illegal header value b'Bearer '`**？
A: `.env` 中的 `COMPANION_WHISPER_API_KEY` 或 `COMPANION_TTS_API_KEY` 为空。填入有效 Key 或设置 `COMPANION_ENABLE_VOICE=false`。

**Q: 能否在本地也跑 Neo4j / Redis？**
A: 可以。Windows 用户可安装 [Redis for Windows](https://github.com/tporadowski/redis/releases) 和 [Neo4j Desktop](https://neo4j.com/download/)。然后在 `.env` 中设置 `COMPANION_LITE_MODE=false` 并配置对应连接地址即可。

**Q: 如何打包给其他人使用？**
A: 本地包只需要 `shared/` + `core_orchestrator/` + `persona_engine/` + `memory_system/` + `voice_layer/` + `action_layer/` + `pyproject.toml` + `.env.lite` + `scripts/run_local.*`。接收方安装 Python 依赖后即可运行，无需 Docker。
