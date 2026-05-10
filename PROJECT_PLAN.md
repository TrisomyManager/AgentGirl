# 陪伴类 AI 智能体项目执行计划

> 版本：V4.1
> 日期：2026-05-07
> 当前阶段：Phase 3 · 人格连续性闭环 · 可调试状态收敛

---

## 0. 项目定位：内部技术原型 · 模块化通用能力库

### 两条核心定位

1. **当前工程是内部提前做的技术原型 Demo**，不绑定任何具体商业项目，不与任何商务报价挂钩。
2. **最终目标是所有模块都可以独立拆开接入任意第三方数字生命项目**，包括但不限于"小汐"项目。

```
companion-ai（本仓库）= 通用陪伴 AI 模块库 + 一个参考集成 demo
  ├── 通用模块（每个都要可独立拆出去）
  │   ├── persona_engine        — 人格/情绪/关系/语气
  │   ├── memory_system         — 工作记忆/向量/图谱/沉淀
  │   ├── voice_layer           — 实时 ASR/TTS/VAD/打断
  │   ├── action_executor       — 插件式动作 + 主动推送
  │   ├── safety_guard (待建)    — OOC / 安全边界
  │   ├── user_profile (待建)    — 结构化用户画像
  │   ├── onboarding (待建)      — 0-1 破冰流程
  │   ├── gateway_adapter       — 多平台 / 多宿主接入适配
  │   └── device_coordination   — 跨设备协同
  ├── 契约层
  │   └── shared_contracts (待建) — 纯模型 + 事件类型，零依赖
  ├── 运行时层（宿主可注入或替换）
  │   └── shared_runtime (待建)  — LLMClient / 配置 / 日志
  └── 参考集成 demo
      ├── core_orchestrator     — 一种 LangGraph 编排实现（不是模块本体）
      └── frontend_app          — 一种 Web 调试台 + Live2D 渲染示例
```

### 关键决策

- **不存在"必交付清单"**：本工程对任何具体项目都不承担交付承诺。任何模块的"完成度"以**对外契约稳定 + 可独立运行 + 可独立集成**为衡量标准，而不是"对账某份功能清单"。
- **`core_orchestrator` 是参考实现，不是模块本体**：第三方接入不应被迫使用我们的编排器。模块通过契约对外开放，宿主用自己的编排去组合。
- **`frontend_app` + Live2D 是"参考 UI / 验收 demo"**：演示"模块对接得多容易"。第三方可换 Unity / Unreal / Web Three.js / 桌面 / 车机 / MR，本仓库不锁渲染端。
- **去商业化口径**：本计划之前所有"小汐 ¥XX万 / 报价表 / 子集 / 灵魂工程必交付"措辞全部废弃。

---

## 1. 当前判断

工程已经具备完整的"陪伴 AI demo"形态（FastAPI 单体 + LangGraph 编排 + 实时语音 + 记忆双层 + 行动执行器 + Live2D 前端），但**模块的"独立可拆性"远低于代码分包给人的直觉**。要走到"任意第三方都能拆装"，最大的三道墙是：

1. **`shared/` 是隐性强耦合中心**：基础设施（日志/配置）与业务级东西（LLMClient / prompt_engine）混在一起。任何模块拆出去都要把 `shared/` 整体拖走。
2. **反向依赖未隔离**：`action_executor` 等模块在文档/状态里声明依赖 `core_orchestrator`，导致拆模块=拖编排器。
3. **协议契约只在文档里，没在代码里**：`ARCHITECTURE.md §4` 列出的 Pub/Sub channel 与 HTTP API 几乎全是 monolithic 进程内函数调用，对外不存在稳定 schema。

之前提的"OOC / ≤30维画像 / 0-1破冰"三项缺口，从"必交付项"降级为"通用能力示例 + 可替换实现"——它们是好东西，但**不再是阻塞当前阶段的关键路径**。

---

## 2. 2026-05-07 状态快照 (V2.3 人格连续性闭环交付)

| 领域 | 状态 | 模块独立可拆性 | 说明 |
|---|---|---|---|
| 单体入口 | ✅ 已完成 | — | `uvicorn main:app --reload --port 8000` 是默认入口 |
| 前端 Web App | ✅ 已完成 | 🟡 中 | 既是 demo UI 又含 Live2D 渲染 |
| 实时语音 | ✅ 已完成 | 🟢 较高 | DashScope SDK 已封装至 providers/，check_arch 直连SDK=0 |
| 人格引擎 | ✅ 已完成 | 🟢 高 | V2.3 runtime.py 单例 + 多角色 + emotion/relationship 持久化 |
| 记忆系统 | 🟡 进行中 | 🟡 中 | working memory 与 prompt_engine 耦合待解 |
| 对话引擎 | ✅ 已完成 | 🔴 参考实现 | LangGraph 编排 + 流式 SSE + 调试台 |
| 行动执行器 | 🟡 进行中 | 🟡 中 | 5 个 handler，主动性模块待状态闭环稳定后扩展 |
| 新用户引导 | 🟢 已打通 | 🟢 高 | /onboarding/* 端点 + OnboardingFlow + user_profile 联动 |
| 用户画像 | 🟢 已打通 | 🟢 高 | SQLiteUserProfileStore + role_id 偏好写入 |
| 安全护栏 | 🟡 骨架 | 🟡 中 | BLOCK/WARN 分级 + PII 正则，已接入输入/输出 |
| 调试台 | 🟢 已完善 | 🟢 高 | /debug/state 完整人格快照 + /personas + /prompt_preview |
| 协议契约 | 🟢 已完成 | 🟢 高 | shared_contracts 已物理化 |

---

## 3. V2.3 已完成交付

### 目标 A：人格连续性闭环 ✅

每轮对话真实更新并影响下一轮的状态链路：

- `persona_engine/runtime.py` — 进程级 EmotionEngine + RelationshipTracker 单例
- `_recall_memory_monolithic` 从 emotion_engine / relationship_tracker 读持久化状态（不再每轮重置）
- `node_sync_memory` 写回 emotion_state + relationship_metrics + user_profile 更新

完成标准：
- 同一个用户连续聊 10 轮后，关系指标持续增长、情绪随对话浮动、回复风格受人/情绪/关系/记忆共同影响
- 141 tests pass，check_arch [ok]

### 目标 B：架构 P0 收口 ✅

- 单角色硬编码 37→24（production code 全清，state_machine/handlers/onboarding/prompt_engine/realtime 全部去"小暖"）
- voice_layer DashScope SDK 迁移至 providers/dashscope.py 封装层 → check_arch 直连SDK=0
- check_arch.py 增加 providers/ 目录 SDK 检查豁免规则

### 目标 C：onboarding → user_profile → persona 链路 ✅

- `/orchestrator/onboarding/start | answer | status` 端点
- `OnboardingFlow` 动态读 `persona_store.list_available_personas()`
- `apply_to_profile` → `SQLiteUserProfileStore`
- `_recall_memory_monolithic` 按 `user_profile.preferences.role_id` 加载对应 persona

### 目标 D：调试台 ✅

- `/orchestrator/debug/state` — 完整人格状态快照（system_prompt + emotion_state + relationship_metrics + working_memory + user_profile）
- `/orchestrator/personas` — 可用角色列表
- `/orchestrator/debug/prompt_preview` 增加 intent 字段

---

## 4. 通用化能力（旧 OOC / 画像 / 破冰，重定位为示例）

不再作为本阶段阻塞，但应作为"通用能力示范模块"在 P0 骨架完成后并行推进：

- `safety_guard/`（旧 OOC）：独立模块，规则集**外部可注入**，不锁死任何角色风格
- `user_profile/`（旧 ≤30维画像）：画像 schema 可配置，预置一套通用维度，**不再锁定 30 维**
- `onboarding/`（旧 0-1 破冰）：破冰流程引擎 + 一份默认脚本，第三方可替换

它们各自就是"模块独立可拆"的标杆样例。

---

## 5. 非本阶段重点

- 本地模型部署 / LoRA 微调
- 任何与具体商业项目（含小汐）报价 / 子集 / 必交付清单 相关的对账工作
- Unity / Unreal / 桌面 / 车机 / MR 等具体宿主端的工程化集成
  - 它们都是"未来可能的宿主"，不是"我们要交付的端"
  - 本仓库只保证模块对宿主友好（API/事件/SDK），不替宿主写代码

---

## 6. 验证与基线

### 建议命令

```powershell
cd companion-ai
python -m pytest -q
uvicorn main:app --reload --port 8000

cd frontend_app
npm run build
```

### 当前已知测试结果

2026-05-07 (V2.3 人格连续性闭环交付)：

- `python -m pytest -q --ignore=voice_layer/tests/test_voice.py --ignore=memory_system/tests/test_memory.py`
  - **141 passed / 0 failed**
- `python tools/check_arch.py --check` — [ok] 与 baseline 对比无新增违规
- 架构基线: 反向依赖=0, 直连SDK=0, 横向耦合=1 (action_layer→action_executor deprecated), 硬编码=25 (doc+test)

### 新增基线门槛（随 P0 落地后启用）

- 模块依赖图：业务模块 → `shared_contracts/` 单向（自动校验）
- 契约测试：每个模块 `openapi.yaml` 与实际接口一致
- `examples/integration_minimal/` smoke test 在 CI 中绿

---

## 7. 执行顺序建议

**P0 — 可拆性骨架（已完成 ✅）**
1. ✅ 拆 `shared/` → `shared_contracts/` + `shared_runtime/`
2. ✅ 反向依赖清理 + importlinter 契约 + PersonaRegistry 多角色
3. ✅ P0 收口：去单角色硬编码 + DashScope SDK 解耦
4. ✅ 9 模块 README + examples + integration_minimal

**P1 — 人格连续性闭环（本次交付 ✅）**
5. ✅ `persona_engine/runtime.py` — 进程级 EmotionEngine + RelationshipTracker
6. ✅ `_recall_memory_monolithic` 读持久化 emotion/relationship 状态
7. ✅ `node_sync_memory` 写回 emotion + relationship + user_profile 更新
8. ✅ onboarding → user_profile → persona role_id 主链路
9. ✅ 调试台 /debug/state + /personas + /onboarding/*

**P2 — 主动性 & 物理清理（下一波次）**
10. 🔲 主动性模块：到点提醒 / 长期未互动问候 / 记忆触发纪念日
11. 🔲 物理删除 deprecated shim（shared/ 和 action_layer/ 的 re-export）
12. 🔲 voice_layer ASRClient 从字符串 provider 分发改为 Protocol 注入
13. 🔲 working memory LLM 摘要器替代 bag-of-words 启发式

---

## 8. 宿主无关：集成路径全景

```
通用模块（本仓库）
  persona_engine / memory_system / voice_layer /
  action_executor / safety_guard / user_profile /
  onboarding / gateway_adapter / device_coordination
       │         │         │
       │ HTTP / SSE / WS / Pub-Sub（基于 shared_contracts）
       ▼         ▼         ▼
  ┌──────────────────────────────────────────────┐
  │          任意宿主（hosts，对模块透明）         │
  │                                              │
  │  · 我们的参考 demo（core_orchestrator + Web）│
  │  · Unity / Unreal 客户端                     │
  │  · 桌面陪伴 / 车机 / MR (Vision Pro)         │
  │  · 第三方 IM / 微信生态                      │
  │  · 第三方数字人 / 数字生命平台（含小汐）       │
  └──────────────────────────────────────────────┘
```

本仓库**不**为任一宿主做工程化交付；只保证模块对外契约稳定、文档齐全、示例可跑。

---

## 9. 交接约定

后续只要代码真实状态发生变化，至少同步这三处：

1. `companion-ai/core_orchestrator/project_status.py`
2. `AI_HANDOFF.md`
3. 本文件 `PROJECT_PLAN.md`

其中：

- 页面可视化以 `project_status.py` 为直接数据源
- `AI_HANDOFF.md` 用于快速接手
- `PROJECT_PLAN.md` 表达接下来要做什么（口径：模块化原型 / 宿主无关）

这三者必须保持同口径，不得再混入"商务报价 / 必交付清单 / 子集对账"措辞。
