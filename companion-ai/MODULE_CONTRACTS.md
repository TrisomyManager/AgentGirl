# Companion AI — 模块接口契约文档

> 版本：V1.0
> 用途：支持各模块独立开发、独立测试、独立部署
> 原则：模块之间仅通过本文档定义的接口通信，禁止直接代码耦合

---

## 1. 总体架构

```
frontend_app (Vue 3) ──HTTP/WebSocket──► main.py:8000 (统一入口)
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
            gateway_adapter            core_orchestrator          persona_engine
               :8000                      :8100                     :8101
                    │                         │                         │
                    │                    ┌────┴────┬────────┐          │
                    │                    ▼         ▼        ▼          │
                    │              memory_system voice_layer action_layer
                    │                  :8102       :8103       :8104
                    │                                              │
                    └──────────────────────────────────────────────┘
                                           │
                                    device_coordination :8105
```

**运行模式**：
- **单体模式 (Monolithic)**：`uvicorn main:app --port 8000`，所有模块在一个进程
- **微服务模式 (Microservice)**：`uvicorn {module}.main:app --port 8xxx`，每个模块独立进程

---

## 2. 接口规范总览

| 接口类型 | 用途 | 格式 |
|---------|------|------|
| **REST API** | 同步请求/响应 | JSON over HTTP |
| **WebSocket** | 实时音频流、动作帧推送 | Binary/JSON |
| **Redis Pub/Sub** | 异步事件通知 | JSON |
| **共享数据库** | 持久化存储 | 各自独立 schema |

**禁止**：
- 禁止模块 A `import` 模块 B 的内部实现
- 禁止模块 A 直接访问模块 B 的数据库表
- 禁止模块间通过全局变量通信

---

## 3. 模块详细契约

### 3.1 gateway_adapter（前端网关）

| 属性 | 值 |
|------|-----|
| 端口 | 8000（单体）/ 8006（微服务） |
| 职责 | 前端统一入口、WebSocket 长连接、多平台消息适配 |

**暴露接口**：

| 端点 | 方法 | 请求 | 响应 | 说明 |
|------|------|------|------|------|
| `/gateway/ws/{user_id}` | WebSocket | binary/JSON | JSON | 前端长连接 |
| `/gateway/send` | POST | `{user_id, platform, content, voice_url, action_sequence}` | `{success, message_id}` | 发送消息 |
| `/gateway/broadcast` | POST | `{user_id, content, exclude_platforms}` | `{success, sent_to[]}` | 广播消息 |
| `/gateway/receive` | POST | `{user_id, platform, content, ...}` | `{success, session_id}` | 接收平台消息 |
| `/gateway/sessions/{user_id}` | GET | - | `{sessions[]}` | 会话列表 |

**依赖的外部服务**：
- core_orchestrator: `POST /orchestrator/turn`

**独立开发 Mock**：
```python
# 不需要 core_orchestrator，直接返回固定回复
@app.post("/gateway/send")
async def mock_send(body):
    return {"success": True, "message_id": "mock-001"}
```

---

### 3.2 core_orchestrator（核心编排）

| 属性 | 值 |
|------|-----|
| 端口 | 8000（单体共享）/ 8100（微服务） |
| 职责 | LangGraph 状态机、Prompt 组装、模块调度 |

**暴露接口**：

| 端点 | 方法 | 请求 | 响应 | 说明 |
|------|------|------|------|------|
| `/orchestrator/turn` | POST | `TurnRequest` | `TurnResponse` | 主入口 |
| `/orchestrator/health` | GET/POST | - | `{status, service}` | 健康检查 |
| `/orchestrator/status` | GET | - | `{modules[]}` | 模块状态 |

**调用的下游接口**：

| 被调用方 | 端点 | 用途 |
|---------|------|------|
| persona_engine | `POST /persona/get_profile` | 获取人格+情感 |
| persona_engine | `POST /persona/generate_response` | LLM 生成回复 |
| memory_system | `POST /memory/recall` | 语义检索记忆 |
| memory_system | `POST /memory/store` | 存储对话 |
| voice_layer | `POST /voice/synthesize` | TTS |
| action_layer | `POST /action/generate` | 生成动作序列 |
| device_coordination | `POST /device/send_command` | 发送设备指令 |
| gateway_adapter | `POST /gateway/send` | 发送响应到前端 |

**独立开发 Mock**：
```python
# 下游模块未就绪时，直接返回 fallback
@app.post("/orchestrator/turn")
async def mock_turn(body):
    return {
        "turn_id": "mock-001",
        "assistant_message": "我在呢，你继续说。",
        "emotion": "calm",
    }
```

---

### 3.3 persona_engine（人格引擎）

| 属性 | 值 |
|------|-----|
| 端口 | 8101 |
| 职责 | 人格定义、情感状态机、关系追踪、语气生成 |

**暴露接口**：

| 端点 | 方法 | 请求 | 响应 | 说明 |
|------|------|------|------|------|
| `/persona/get_profile` | POST | `{user_id}` | `{persona, emotion, relationship, tone_text}` | 获取完整人格 |
| `/persona/update_emotion` | POST | `{user_id, event_type, sentiment, ...}` | `{new_emotion}` | 更新情感 |
| `/persona/relationship` | POST | `{user_id}` | `{relationship}` | 关系指标 |
| `/persona/daily_digest` | POST | `{user_id}` | `{digest, relationship, emotion}` | 每日关系总结 |
| `/persona/generate_response` | POST | `{user_id, user_message, system_prompt, emotion, relationship}` | `{assistant_message, new_emotion, sentiment}` | LLM 生成 |

**依赖的外部服务**：
- LLM API（OpenAI/Anthropic）
- PostgreSQL/Redis（best-effort，失败时降级内存存储）

**独立开发 Mock**：
```bash
# 测试人格加载
curl -X POST http://localhost:8101/persona/get_profile \
  -d '{"user_id": "test"}'

# 测试回复生成（需要 LLM API Key）
curl -X POST http://localhost:8101/persona/generate_response \
  -d '{"user_id": "test", "user_message": "你好", "system_prompt": "你是小暖"}'
```

**关键文件**：
- `persona_engine/data/soul.yaml` — 人格定义（可修改，重启生效）

---

### 3.4 memory_system（记忆系统）

| 属性 | 值 |
|------|-----|
| 端口 | 8102 |
| 职责 | 向量记忆、对话归档、五阶段记忆流水线、用户画像 |

**暴露接口**：

| 端点 | 方法 | 请求 | 响应 | 说明 |
|------|------|------|------|------|
| `/memory/store` | POST | `{user_id, category, content, importance, emotion_tags}` | `MemoryEntry` | 存储记忆 |
| `/memory/recall` | POST | `{query, user_id, top_k, include_graph}` | `MemoryRecallResult` | 语义检索 |
| `/memory/graph_query` | POST | `{cypher, parameters}` | `List[dict]` | 知识图谱查询 |
| `/memory/pipeline/trigger` | POST | `{turn_id, user_message, assistant_message}` | `{task_id}` | 触发流水线 |
| `/memory/user/{user_id}/summary` | GET | - | `{total_memories, avg_importance, ...}` | 用户摘要 |
| `/memory/maintenance/decay` | POST | - | `{expired_deleted}` | 清理过期记忆 |

**依赖的外部服务**：
- PostgreSQL + pgvector（主存储）
- Neo4j（知识图谱，可选）
- OpenAI API（embeddings）

**独立开发 Mock**：
```bash
# 存储记忆
curl -X POST http://localhost:8102/memory/store \
  -d '{"user_id": "u1", "category": "preference", "content": "喜欢咖啡"}'

# 召回记忆
curl -X POST http://localhost:8102/memory/recall \
  -d '{"query": "喝什么", "user_id": "u1", "top_k": 5}'
```

**Lite Mode 行为**：
- 使用 SQLite 替代 PostgreSQL
- 向量检索退化为 Python 计算的余弦相似度
- 知识图谱被跳过

---

### 3.5 voice_layer（语音层）

| 属性 | 值 |
|------|-----|
| 端口 | 8103 |
| 职责 | ASR、TTS、语音流管理、VAD |

**暴露接口**：

| 端点 | 方法 | 请求 | 响应 | 说明 |
|------|------|------|------|------|
| `/voice/transcribe` | POST | `multipart: audio file + language` | `{text, confidence, emotion}` | 语音转文字 |
| `/voice/synthesize` | POST | `{text, voice_id, emotion, speed}` | `{audio_url, duration_ms}` | 文字转语音 |
| `/voice/stream` | WebSocket | binary audio chunks | JSON transcription | 实时语音流 |

**依赖的外部服务**：
- OpenAI Whisper / Groq（ASR）
- Fish Audio S2 / ChatTTS（TTS）

**独立开发 Mock**：
```bash
# ASR 测试
curl -X POST http://localhost:8103/voice/transcribe \
  -F "audio=@test.wav" -F "language=zh"

# TTS 测试
curl -X POST http://localhost:8103/voice/synthesize \
  -d '{"text": "你好", "emotion": "happy"}' --output output.mp3
```

---

### 3.6 action_layer（动作层）

| 属性 | 值 |
|------|-----|
| 端口 | 8104 |
| 职责 | 动作意图转换、动作模板、唇形同步 |

**暴露接口**：

| 端点 | 方法 | 请求 | 响应 | 说明 |
|------|------|------|------|------|
| `/action/generate` | POST | `{turn_id, emotion, text, audio_duration_ms}` | `ActionSequence` | 生成动作序列 |
| `/action/lip_sync` | POST | `{text, duration_ms, fps}` | `[{frame, lip_shape}]` | 唇形关键帧 |
| `/action/templates` | GET | - | `[{name, description}]` | 动作模板列表 |

**依赖的外部服务**：无（纯内部逻辑）

**独立开发 Mock**：
```bash
curl -X POST http://localhost:8104/action/generate \
  -d '{"emotion": "happy", "text": "你好", "audio_duration_ms": 1500}'
# 返回：frames 列表，每个帧有 action_type 和 duration_ms
```

---

### 3.7 device_coordination（设备协同）

| 属性 | 值 |
|------|-----|
| 端口 | 8105 |
| 职责 | 设备注册、MQTT 消息总线、任务分发 |

**暴露接口**：

| 端点 | 方法 | 请求 | 响应 | 说明 |
|------|------|------|------|------|
| `/device/register` | POST | `{device_id, device_type, device_name, ...}` | `{success, device}` | 注册设备 |
| `/device/heartbeat` | POST | `{device_id}` | `{success}` | 心跳 |
| `/device/list/{user_id}` | GET | `?online_only=true` | `{devices[]}` | 设备列表 |
| `/device/send_command` | POST | `{device_id, command, payload}` | `{success}` | 发送指令 |
| `/device/broadcast` | POST | `{user_id, command, payload}` | `{success, sent_to[]}` | 广播指令 |

**依赖的外部服务**：
- MQTT broker

**独立开发 Mock**：
```bash
# 注册虚拟设备
curl -X POST http://localhost:8105/device/register \
  -d '{"device_id": "pc-001", "device_type": "pc", "device_name": "我的电脑"}'

# 发送指令
curl -X POST http://localhost:8105/device/send_command \
  -d '{"device_id": "pc-001", "command": "play_music"}'
```

---

## 4. 事件总线契约（Redis Pub/Sub）

| Channel | 方向 | 载荷 | 说明 |
|---------|------|------|------|
| `companion:turn:start` | gateway → core | `TurnStartEvent` | 新对话轮开始 |
| `companion:turn:end` | core → gateway | `TurnEndEvent` | 对话轮结束 |
| `companion:memory:sync` | core → memory | `MemorySyncEvent` | 触发记忆存储 |
| `companion:action:generate` | core → action | `ActionGenerateEvent` | 请求动作生成 |
| `companion:voice:synthesize` | core → voice | `VoiceSynthesizeEvent` | 请求语音合成 |
| `companion:persona:update` | core → persona | `PersonaUpdateEvent` | 更新人格状态 |
| `companion:device:command` | core → device | `DeviceCommandEvent` | 发送设备指令 |

**事件定义文件**：`shared/events.py`

---

## 5. 数据模型契约（Pydantic）

**核心模型定义文件**：`shared/models.py`

| 模型 | 用途 | 关键字段 |
|------|------|----------|
| `UserProfile` | 用户身份 | user_id, display_name, platform, language |
| `EmotionState` | 情感状态 | primary, intensity, valence, arousal |
| `RelationshipMetrics` | 关系指标 | intimacy, trust, familiarity, affection |
| `PersonaProfile` | 人格定义 | name, core_traits, communication_style |
| `TurnContext` | 对话上下文 | turn_id, session_id, user, user_message |
| `MemoryEntry` | 记忆条目 | entry_id, category, content, importance |
| `ActionSequence` | 动作序列 | frames[], total_duration_ms |
| `DeviceInfo` | 设备信息 | device_id, device_type, capabilities, is_online |

---

## 6. 独立开发检查清单

每个模块作为独立 Claude 工程开发时，确保：

- [ ] 模块可独立启动：`uvicorn {module}.main:app --port 8xxx`
- [ ] 模块有独立的健康检查端点：`GET /health`
- [ ] 所有外部依赖可用 Mock/Stub 替代
- [ ] 单元测试不依赖其他模块
- [ ] 接口契约文档与实际代码一致

### 6.1 推荐的独立开发顺序

```
1. persona_engine → 最简单，只需 LLM API
2. memory_system → 需要数据库，可用 SQLite
3. voice_layer → 需要 ASR/TTS API
4. action_layer → 无外部依赖
5. device_coordination → 需要 MQTT broker
6. core_orchestrator → 最后集成，依赖所有下游
7. gateway_adapter → 最后，依赖 core
```

---

## 7. 配置环境变量

**基础配置**（所有模块共用）：
```bash
# 必需
COMPANION_OPENAI_API_KEY=sk-xxx          # LLM API Key
COMPANION_DEFAULT_LLM_MODEL=gpt-4o       # 默认模型

# 可选
COMPANION_LITE_MODE=true                 # 无 Docker 模式（SQLite + 内存）
COMPANION_ENABLE_VOICE=false             # 禁用语音模块
COMPANION_ENABLE_ACTION_2D=false        # 禁用动作模块
COMPANION_ENABLE_DEVICE_COORDINATION=false  # 禁用设备模块

# 语音（可选）
COMPANION_TTS_API_KEY=xxx
COMPANION_WHISPER_API_KEY=xxx
```

---

## 8. Hermes 复用边界

| 模块 | Hermes 复用 | 复用方式 |
|------|------------|----------|
| gateway_adapter | `gateway/platforms/telegram.py` | 适配器模式参考 |
| gateway_adapter | `gateway/platforms/discord.py` | 适配器模式参考 |
| core_orchestrator | `agent/prompt_builder.py` | SOUL.md 注入逻辑参考 |
| core_orchestrator | `tools/registry.py` | 工具注册调度复用 |
| persona_engine | `agent/prompt_builder.py` | 人格加载逻辑参考 |
| memory_system | `agent/memory_manager.py` | 多 provider 架构参考 |

---

## 附录：curl 测试速查

```bash
# 1. 启动单体模式
COMPANION_LITE_MODE=true uvicorn main:app --reload --port 8000

# 2. 测试健康
curl http://localhost:8000/health

# 3. 测试人格
curl -X POST http://localhost:8000/persona/get_profile \
  -H "Content-Type: application/json" -d '{"user_id":"u1"}'

# 4. 测试对话
curl -X POST http://localhost:8000/orchestrator/turn \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","user":{"user_id":"u1","display_name":"Test"},"user_message":"你好","platform":"app"}'

# 5. 测试记忆存储
curl -X POST http://localhost:8000/memory/store \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","category":"preference","content":"喜欢咖啡"}'

# 6. 测试记忆召回
curl -X POST http://localhost:8000/memory/recall \
  -H "Content-Type: application/json" \
  -d '{"query":"喝什么","user_id":"u1","top_k":5}'
```
