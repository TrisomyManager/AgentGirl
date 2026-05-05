# 陪伴类 AI 智能体项目执行计划

> 版本：V2.3  
> 日期：2026-05-05  
> 当前阶段：Phase 1.5 · 实时语音 MVP 收敛期

---

## 1. 当前判断

项目已经从“搭骨架”进入“收敛关键链路”的阶段。

和 2026-04-30 相比，最大的变化不是又多了多少远期规划，而是这些能力已经真正落地：

- 单体入口 `companion-ai/main.py` 已可作为默认开发入口
- 实时语音通话链路已跑通
- 前端已具备聊天、通话、记忆查看、状态可视化能力
- LLM / Voice Provider 已支持运行时配置与持久化

当前真正拖慢整体可交付性的，是下面三类问题：

1. Prompt 组装仍未收口，system prompt 还在硬编码
2. 记忆系统的模型分层和测试兼容还不稳
3. 文本聊天主路径和实时语音路径的体验成熟度不一致

---

## 2. 2026-05-04 状态快照

| 领域 | 状态 | 说明 |
|---|---|---|
| 单体入口 | 已完成 | `uvicorn main:app --reload --port 8000` 是默认入口 |
| 前端 Web App | 已完成 | 聊天、通话、设置、记忆库、状态面板都可用 |
| 实时语音 | 已完成 | VAD、AudioWorklet、WebSocket 双向流、TTS chunk 播放已打通 |
| 人格引擎 | 基本完成 | 情绪、关系指标、daily digest 已有实现 |
| 记忆系统 | 进行中 | 向量检索已在，working/persistent memory 尚未补齐 |
| 动作执行器 | 规划中 | 主动提醒、插件动作、外部查询还未形成闭环 |
| 跨设备协同 | 规划中 | 设备注册与调度仍未成为本阶段主线 |

---

## 3. 未来两周的真实目标

### 目标 A：收敛 Prompt Engine

目标：

- 把 `core_orchestrator/state_machine.py` 的 system prompt 硬编码迁到共享层
- 让人格文件、关系摘要、用户画像、召回记忆都能通过统一入口注入

完成标准：

- prompt 拼装逻辑不再散落在状态机内部
- 能明确区分基础人格、会话上下文、关系状态、记忆召回四类输入
- 为后续调试台展示完整 prompt 链路打基础

### 目标 B：稳定记忆系统

目标：

- 修复 sqlite 测试环境下的向量字段绑定问题
- 明确 working memory 和 persistent memory 的职责边界

完成标准：

- `memory_system/tests/test_memory.py` 能稳定通过
- 对话上下文使用的临时记忆和长期沉淀记忆不再混在一个抽象里
- 记忆摘要失败时有清晰降级路径

### 目标 C：补主聊天流式输出

目标：

- 让聊天主面板支持渐进式文本反馈，而不仅是语音通话支持流式

完成标准：

- 前端消息区能逐步展示模型输出
- 主聊天与实时语音共用一套更一致的流式状态语义
- 不因 provider 不支持 streaming 而破坏当前可用路径

---

## 4. 非本阶段重点

以下方向保留，但不建议在当前阶段抢占主优先级：

- 3D 数字人或复杂动作生成
- 全量跨设备协同
- 本地模型部署与 LoRA 微调
- 知识图谱深度玩法
- 复杂插件系统

判断标准很简单：

如果一个工作不能直接提升“当前对话闭环稳定性、实时语音体验一致性、接手成本可控性”，就不该排到本阶段前面。

---

## 5. 验证与基线

### 建议命令

```powershell
cd companion-ai
python -m pytest -q
uvicorn main:app --reload --port 8000

cd frontend_app
npm run build
```

### 当前已知测试结果

2026-05-05 本地结果：

- `python -m pytest -q`
  - **97 passed / 0 failed**

修复点：

- `pyproject.toml`
  - 显式声明 `numpy` 依赖，避免 `voice_layer` 在干净 venv 中
    `ModuleNotFoundError` 阻塞整组 collect。
- `shared/tests/test_prompt_engine.py`
  - 英文断言已对齐 `shared/prompt_engine.py` 的中文 prompt 实现。
- `memory_system`
  - 上一轮的 SQLite 向量绑定问题在 `memory_system/db.py` /
    `vector_store.py` 改动后已恢复绿色。

需要继续观察的：

- `voice_layer` 的真实音频集成在 CI / 干净环境仍依赖 `ffmpeg`
  与本地模型，目前是通过 monkeypatch 避免硬依赖。

---

## 6. 执行顺序建议

推荐严格按这个顺序推进：

1. Prompt Engine
2. memory_system 稳定性
3. 主聊天流式输出
4. action / device 能力

如果顺序反过来，结果通常会是：

- 功能面越来越大
- 对话质量却不稳定
- 交接文档越来越难写

---

## 7. 交接约定

后续只要代码真实状态发生变化，至少同步这三处：

1. `companion-ai/core_orchestrator/project_status.py`
2. `AI_HANDOFF.md`
3. 本文件 `PROJECT_PLAN.md`

其中：

- 页面可视化以 `project_status.py` 为直接数据源
- `AI_HANDOFF.md` 用于快速接手
- `PROJECT_PLAN.md` 用于表达接下来要做什么

这三者必须保持同口径，避免再次出现“页面、文档、代码三套真相”。
