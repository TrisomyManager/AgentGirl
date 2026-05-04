# 陪伴类 AI 智能体 — 分阶段项目执行计划

> 版本：V2.1 — 基于代码现状更新
> 日期：2026-04-30
> 状态： Phase 0 已完成首轮收敛，单体入口和测试基线已可用，接下来应继续收敛提示词/依赖边界并推进 MVP 对话闭环

---

## 0. 现状诊断

### 0.1 已完成的骨架（值得保留）

| 模块 | 现状 | 评估 |
|------|------|------|
| `shared/models.py` | Pydantic 模型完整 | 保留，补字段即可 |
| `shared/events.py` | 事件类型定义完整 | 保留 |
| `shared/config.py` | 统一配置管理 | 保留，需增加模型路由配置 |
| `core_orchestrator/state_machine.py` | LangGraph 状态机完整 | 保留，但 system prompt 硬编码需重构 |
| `core_orchestrator/orchestrator.py` | 编排器生命周期管理 | 保留 |
| `persona_engine/main.py` | FastAPI 生命周期完整 | 保留，但需解耦数据库依赖 |
| `memory_system/main.py` | 服务入口完整 | 保留 |
| `main.py` | 单体 FastAPI 入口已可运行 | 保留，作为本地开发默认入口 |
| `shared/database/__init__.py` | 统一 async engine/session 已落地 | 保留，继续推动各模块收敛 |
| `shared/llm_client.py` | 统一 LLM client 已落地 | 保留，后续补模型路由/流式能力 |

### 0.2 关键问题（必须解决）

| 问题 | 影响 | 严重度 |
|------|------|--------|
| **文档与代码状态不同步**：README/计划仍按“待实现”描述单体入口、共享数据库层 | 误导接手和排期判断 | P0 |
| **LLM 调用链路绕远**：core → HTTP → persona_engine → llm_client | 延迟高、调试难 | P0 |
| **System Prompt 硬编码**在 `state_machine.py` | 无法切换人格、无法复用 Hermes 的 SOUL.md 注入 | P0 |
| **统一数据库层未完全吃透**：仍有模块自行维护 Postgres/Redis 生命周期 | 连接池泄漏风险、职责重复 | P1 |
| **各模块只有接口框架**：ASR/TTS/向量检索/动作生成均无实际调用 | 无法端到端运行 | P1 |
| **与 Hermes 集成边界模糊**：哪些复用、哪些自研没有文档化 | 重复造轮子或过度耦合 | P1 |

### 0.3 与 Hermes 的复用边界（已明确）

```
Hermes 复用清单：
  ✅ gateway/platforms/* — Telegram/Discord/Slack/WeChat 适配器（直接复用）
  ✅ tools/ — 40+ 内置工具（通过 adapter 暴露）
  ✅ agent/prompt_builder.py — SOUL.md / AGENTS.md / 技能索引注入
  ✅ agent/memory_manager.py — 多 provider 记忆架构（概念复用）
  ✅ agent/context_compressor.py — 上下文压缩（概念复用）
  ✅ cron/ — 定时任务调度（复用或参考）

Hermes 不复用（自研替代）：
  ❌ agent/run.py — 回合循环（被 LangGraph 替代）
  ❌ agent/models_dev.py — 模型路由（被 LiteLLM 替代）
  ❌ memory_provider.py — 具体记忆实现（被 memory_system 替代）
```

---

## 1. 总体策略

### 1.1 核心原则

1. **先单体，后拆分**：Phase 0~2 全部模块在一个 FastAPI 进程内运行（通过依赖注入），Phase 3 再考虑拆微服务。
2. **先文本，后语音/动作**：先让核心对话流跑起来，再叠加多模态。
3. **先云 API，后本地模型**：MVP 全部走云端 API，降低硬件门槛。
4. **复用优先**：能用 Hermes 的绝不重写，能调云 API 的绝不本地部署。

### 1.2 不做的事（明确范围）

| 阶段 | 不做 |
|------|------|
| Phase 0~2 | 不拆分微服务、不部署 Kubernetes、不实现 3D 数字人 |
| Phase 0~1 | 不集成 ASR/TTS、不实现动作生成、不做跨设备协同 |
| Phase 0 | 不加任何新功能，只做整顿 |
| 全程 | 不做本地模型部署、不做 LoRA 微调、不做知识图谱 |

---

## 2. Phase 0：架构整顿（2~3 周）

**目标**：解决技术债，建立可增量开发的健康代码基线。

### 2.1 模块解耦与统一数据层

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| `shared/database/` | 已落地统一 SQLAlchemy async engine + session factory | 下一步是收敛剩余模块的直连连接 |
| `shared/llm_client.py` | 已落地统一 LLM 客户端 | 下一步补流式、fallback 和更清晰的模型路由 |
| `shared/prompt_engine.py` | 尚未落地 | 仍是后续优先项 |
| 修复 `persona_engine` 对 `memory_system.db` 的直接依赖 | 已完成，当前可正常 import | 下一步继续减少重复生命周期代码 |
| 统一 Redis 客户端 | 部分完成 | 仍需统一入口和生命周期管理 |

### 2.2 运行模式统一

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| 实现单体启动 | 当前通过 `uvicorn main:app --reload --port 8000` 运行 | 后续可再补包级入口 |
| 保留微服务启动 | 各模块仍可 `uvicorn core_orchestrator.main:app --port 8000` 独立启动 | 向后兼容 |
| Lite Mode 完善 | 无 Docker 时自动降级为 SQLite + 内存事件总线 | `/health` 已通过，下一步补真实对话冒烟 |

### 2.3 测试与工程规范

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| 统一测试基座 | pytest + pytest-asyncio + async SQLAlchemy test db | 已跑通，当前 `93 passed` |
| mypy 零报错 | 修复现有类型错误 | `mypy shared/ core_orchestrator/ persona_engine/ memory_system/` 通过 |
| 依赖锁定 | 生成 `requirements.lock` | CI 可复现安装 |

### Phase 0 里程碑

- [x] `pytest` 全绿（当前 93 项通过）
- [x] 单体入口启动后 `/health` 返回健康状态
- [ ] Lite Mode 下无需 Docker 可完整运行文本对话

---

## 3. Phase 1：核心对话 MVP（4~6 周）

**目标**：实现一个可对话、有人格、有长期记忆的陪伴 AI，通过 Web/命令行即可交互。

### 3.1 人格引擎（persona_engine）

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| Soul YAML 加载 | 从 `data/soul.yaml` 加载人格，支持热更新 | 修改 YAML 后重启即生效 |
| 情感状态机 | 基于 PAD 模型（Pleasure-Arousal-Dominance）的情感变化 | 对话后情感状态有合理变化 |
| 关系指标追踪 | 亲密度/信任度/熟悉度，每次交互自动微调 | 数据库中可查询关系历史 |
| 动态语气生成 | 根据情感状态调整 LLM 的 temperature + system prompt suffix | 悲伤时回应更温柔 |
| 关系总结生成 | 每日首次对话时生成「关系总结」注入 prompt | prompt 中可见近期关系变化 |

### 3.2 记忆系统（memory_system）

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| 对话归档 | 每轮对话存入 Postgres | 可查询历史对话 |
| 向量检索 | pgvector 实现语义检索，召回 top-5 相关记忆 | 输入"我喜欢什么"能召回偏好 |
| 五阶段记忆流水线（简化版） | Celery worker 异步抽取：事实/情感/偏好 | 后台任务不阻塞对话 |
| 用户画像 | 自动汇总用户基本信息、偏好 | prompt 中可见用户摘要 |

### 3.3 核心编排（core_orchestrator）

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| Prompt 组装 | 整合：SOUL.md + 情感状态 + 关系指标 + 记忆上下文 + 用户画像 | 发送给 LLM 的 prompt 结构清晰 |
| 意图识别 | LLM-as-intent-router（chat / memory_query / device_command） | 意图分类准确率 > 80% |
| 工具调度入口 | 复用 Hermes tools/ 通过 adapter 暴露 | 可调用 search / calculator 等 |
| 对话流完整闭环 | receive → classify → recall → generate → send → sync_memory | 端到端延迟 < 3s（云 API） |

### 3.4 网关适配（gateway_adapter）

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| Web API 接口 | REST API 供前端调用 | 可通过 curl 发送消息并收到回复 |
| 复用 Hermes 平台适配器 | Telegram / Discord 适配器接入 | Telegram Bot 可对话 |
| WebSocket 实时推送 | 支持流式文本返回 | 前端可逐字显示 |

### 3.5 管理后台（Web 调试台）

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| 对话调试台 | 查看每次对话的完整 prompt / 记忆召回 / 情感变化 | 开发者可诊断对话质量 |
| 记忆管理台 | 查看/编辑/删除用户记忆 | 可纠正错误记忆 |
| 人格调试台 | 实时调整情感参数，观察回应变化 | 滑动条调情感，回应对应变化 |
| 关系指标面板 | 可视化用户关系曲线 | 图表展示亲密度历史 |

### Phase 1 里程碑

- [ ] 通过 Web UI 或 Telegram 可与 AI 进行多轮对话
- [ ] 对话中 AI 能记住用户之前说过的话（跨 session）
- [ ] 管理后台可查看每次对话的完整上下文链
- [ ] 人格文件修改后对话风格发生变化
- [ ] 关系指标随对话次数增加而上升

---

## 4. Phase 2：语音 + 动作增强（4~6 周）

**目标**：在文本对话基础上叠加语音输入输出和 2D 角色动作表现。

### 4.1 语音层（voice_layer）

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| ASR 集成 | Whisper API / 阿里云 / Groq，支持情感识别 | 语音输入 → 文本延迟 < 2s |
| TTS 集成 | Fish Audio S2 / ChatTTS API，支持情感语音 | 文本 → 语音延迟 < 2s |
| 语音流管理 | WebSocket 传输音频流 | 前端可实时播放 |
| VAD 集成 | WebRTC VAD 检测语音结束 | 自动识别用户说完 |

### 4.2 动作层（action_layer）

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| 动作意图转换 | LLM 输出 action_intent + emotion_tag | 每轮对话自动产生动作标签 |
| 动作路由 | 根据意图选择动作模板（idle / talk / react_happy / react_sad） | 正确路由率 > 80% |
| 2D 动作生成（简化版） | 不调用通义万相 API（成本高），改用预置动作序列 + 图片切换 | 前端可见角色表情变化 |
| 唇形同步 | TTS 音频时长 → 唇形关键帧插值 | 说话时的口型与音频匹配 |

### 4.3 前端 App（简化版）

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| Web 前端（React/Vue） | 聊天界面 + 角色展示区域 | 可发送消息、显示角色表情 |
| 语音交互 UI | 按住说话 / 自动播放 | 类似微信语音 |
| 角色展示 | 2D 立绘 + 表情切换 | 根据情感标签切换表情图 |
| 移动端适配 | PWA 或 React Native 简化版 | 手机浏览器可用 |

### Phase 2 里程碑

- [ ] 按住说话，AI 语音回复
- [ ] 屏幕上角色根据对话情感改变表情/动作
- [ ] 手机上可用（PWA）
- [ ] 端到端语音延迟 < 5s

---

## 5. Phase 3：工具 + 设备协同（6~8 周）

**目标**：让 AI 能帮用户做事（查天气、发邮件、控制设备），实现跨设备协同。

### 5.1 工具系统

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| 复用 Hermes 工具集 | 将 Hermes tools/ 封装为 companion-ai 可调用的工具 | 可用 Hermes 的 search / shell / file 等工具 |
| 办公能力工具 | 文件解析（PDF/DOCX/XLSX）、代码沙箱（E2B）、表格处理 | 可分析上传的 Excel 文件 |
| 安全沙箱 | 代码执行隔离 | 危险代码不破坏主机 |
| 工具结果注入对话 | 工具执行结果自动追加到对话上下文 | 用户感知不到工具调用过程 |

### 5.2 跨设备协同（device_coordination）

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| 设备注册中心 | 设备上线注册、心跳检测 | 可查看在线设备列表 |
| MQTT 消息总线 | 设备间消息转发 | 手机可向 PC 发送指令 |
| 任务分发 | AI 决策后向指定设备下发任务 | "在电视上播放视频" → 电视执行 |
| 端到端加密 | Syncthing 或自研加密同步 | 设备间通信加密 |

### 5.3 安全与权限

| 任务 | 说明 | 交付标准 |
|------|------|----------|
| JWT 鉴权 | API 请求鉴权 | 未授权请求被拒绝 |
| 命令审批 | 危险操作（删除文件、执行代码）需用户确认 | 高风险操作弹出确认 |
| 输入过滤 | Meta SecAlign 或自研过滤敏感内容 | 不输出有害内容 |
| 审计日志 | 所有工具调用和操作记录 | 可追溯 |

### Phase 3 里程碑

- [ ] AI 可读取并分析用户上传的文件
- [ ] 手机与 PC 可同时登录同一 AI，对话状态同步
- [ ] AI 可控制智能家居设备（如播放音乐）
- [ ] 危险操作需要用户确认

---

## 6. Phase 4：高级能力（按需排期）

**目标**：知识图谱、实时数字人、本地模型部署 —— 在 Phase 0~3 稳定后再启动。

| 能力 | 说明 | 依赖 |
|------|------|------|
| 知识图谱 | Neo4j + GraphRAG，构建人物关系网络 | Phase 1 记忆系统稳定 |
| 实时数字人 | 接入 SoulX-LiveAct / Runway | Phase 2 动作层稳定 |
| 本地模型 | Ollama / vLLM 部署，LoRA 人格微调 | GPU 硬件到位 |
| 跨平台 App | Flutter 完整客户端 | 前端设计资源到位 |
| 自动化 Cron | Hermes cron 复用，定时任务 | Phase 1 核心稳定 |
| 多智能体协作 | CrewAI / AutoGen 多 agent 编排 | 有明确多 agent 场景 |

---

## 7. 团队配置建议（按阶段）

### Phase 0（2~3 周）

| 角色 | 人数 | 职责 |
|------|------|------|
| 技术负责人 | 1 | 架构设计、代码审查、Hermes 复用决策 |
| AI 后端工程师 | 1 | 模块解耦、统一数据层、LLM 客户端 |
| 测试/QA | 0.5 | 测试基座搭建 |

### Phase 1（4~6 周）

| 角色 | 人数 | 职责 |
|------|------|------|
| 技术负责人 | 1 | 架构把控、LLM prompt 调优 |
| AI 后端工程师 | 2 | LangGraph 编排、记忆系统、人格引擎 |
| 前端工程师 | 1 | 管理后台 Web UI |
| 角色体验策划 | 0.5 | 人格文件编写、情感规则设计 |
| 测试/QA | 1 | 端到端测试、人格稳定性测试 |

### Phase 2（4~6 周）

| 角色 | 人数 | 职责 |
|------|------|------|
| 技术负责人 | 1 | 整体协调 |
| 语音/多模态工程师 | 1 | ASR/TTS 集成、音频流 |
| 前端工程师 | 1 | App 前端、角色展示 |
| 技术美术 | 0.5 | 2D 角色立绘、表情素材 |
| 测试/QA | 1 | 语音质量测试、延迟测试 |

### Phase 3（6~8 周）

| 角色 | 人数 | 职责 |
|------|------|------|
| 技术负责人 | 1 | 整体协调 |
| 后端工程师 | 2 | 设备协同、工具系统、安全 |
| DevOps | 0.5 | 部署、监控 |
| 测试/QA | 1 | 安全测试、跨设备测试 |

---

## 8. 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Hermes 版本升级导致复用代码不兼容 | 中 | 高 | 复用层加 adapter 隔离，不直接 import Hermes 内部 |
| 云 API 延迟过高影响体验 | 高 | 中 | 预留本地模型降级路径；异步生成语音/动作 |
| 人格/OOC 不稳定 | 高 | 高 | Phase 1 投入足够时间调 prompt；建立 OOC 测试集 |
| 记忆质量差（召回不准） | 中 | 中 | 先做关键词+向量混合检索，不急于上知识图谱 |
| 跨设备同步复杂度过高 | 中 | 中 | Phase 3 先只做 2 设备（手机+PC），不做全屋智能 |
| 团队人力不足 | 高 | 高 | Phase 0~1 先走通核心，证明可行性后再扩招 |

---

## 9. 立即开始的第一步（本周）

1. **冻结新功能开发**：停止在任何模块添加新能力，专注于 Phase 0 整顿。
2. **建立 `shared/database/`**：把 SQLAlchemy engine + session 抽出来，所有模块统一引用。
3. **修复 `persona_engine` 循环依赖**：删除 `from memory_system.db import`，改为 HTTP 调用或事件总线。
4. **建立统一 LLM 客户端**：`shared/llm_client.py` 封装 LiteLLM，支持多 provider fallback。
5. **跑通单体启动**：`python -m companion_ai` 能启动且所有子模块 health check 通过。

---

## 附录：与 Hermes 的具体复用清单

### 直接复用（代码级）

| Hermes 文件 | companion-ai 用途 |
|------------|-------------------|
| `gateway/platforms/telegram.py` | gateway_adapter Telegram Bot |
| `gateway/platforms/discord.py` | gateway_adapter Discord Bot |
| `gateway/platforms/slack.py` | gateway_adapter Slack Bot |
| `gateway/run.py` | 会话生命周期参考 |
| `tools/search_*.py` | 工具系统搜索类工具 |
| `tools/shell.py` | 命令行工具（需加沙箱） |
| `tools/file_tools.py` | 文件操作工具 |

### 概念复用（参考实现）

| Hermes 文件 | companion-ai 实现 |
|------------|-------------------|
| `agent/prompt_builder.py` | `shared/prompt_engine.py`（简化版） |
| `agent/memory_manager.py` | `memory_system/recall.py`（多 provider 架构） |
| `agent/context_compressor.py` | `core_orchestrator/compressor.py`（上下文压缩） |
| `cron/scheduler.py` | `core_orchestrator/scheduler.py`（定时任务） |
| `agent/skill_commands.py` | `core_orchestrator/tools.py`（技能调用） |
