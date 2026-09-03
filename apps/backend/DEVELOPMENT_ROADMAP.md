# 小暖开发路线图

> 按优先级排列，每项可独立完成。标记 🟢 已完成 / 🟡 待开始 / 🔵 长期规划。

---

## Phase 1：主动会话闭环（V2.5 核心）

| # | 任务 | 状态 | 难度 | 预计工时 | 产出 |
|---|------|------|------|----------|------|
| 1.1 | 实现 ProactiveCareScheduler 基础调度器 | 🟢 已完成 | ⭐⭐ | 4h | `action_executor/proactive_care.py` |
| 1.2 | Orchestrator 新增 `generate_proactive_turn()` 简化生成路径 | 🟢 已完成 | ⭐⭐ | 2h | `orchestrator.py` 新方法 |
| 1.3 | 前端 SSE → Chat 消息注入链路 | 🟢 已完成 | ⭐ | 2h | `useProactivePush` + `useChat` 联动 |
| 1.4 | 调度器配置项（DND/冷却/日上限） | 🟢 已完成 | ⭐ | 1h | `config.py` proactive 配置块 |
| 1.5 | **升级为 HeartFlow 持续思考模式** | 🟡 待开始 | ⭐⭐⭐ | 8h | 从定时轮询升级为 per-user 常驻异步思考任务，持续评估"现在该不该说话" |
| 1.6 | 用户交互 → `last_seen` 正确更新 | 🟡 待开始 | ⭐ | 1h | 修复 `hours_inactive=0` 问题，确保关系追踪器在 Lite 模式下正确更新 |
| 1.7 | 主动关怀规则前端配置 UI | 🟡 待开始 | ⭐⭐ | 4h | `CapabilityPanel` 中的规则开关变可用，支持用户自行启停各类触发规则 |

---

## Phase 2：记忆系统增强（MaiBot 海马体借鉴）

| # | 任务 | 状态 | 难度 | 预计工时 | 产出 |
|---|------|------|------|----------|------|
| 2.1 | **Working Memory 压缩机制** | 🟡 待开始 | ⭐⭐⭐ | 6h | 对超过 N 轮的旧消息进行 LLM 摘要压缩，上下文有效信息量提升 3-5x |
| 2.2 | **遗忘机制**：低频记忆自动降权 | 🟡 待开始 | ⭐⭐⭐ | 6h | `memory_system/` 新增遗忘调度，基于 LRU + 访问频率，软删除 + 可再激活 |
| 2.3 | 双通道记忆检索升级 | 🟡 待开始 | ⭐⭐ | 4h | 向量语义搜索 + 知识图谱关系扩散（参考 PPR），当前已有基础但图谱权重不足 |
| 2.4 | 记忆重要性自动化评分优化 | 🟡 待开始 | ⭐⭐ | 3h | 当前 `importance_score` 依赖 LLM 调用，增加规则辅助评分（频率、时效、情感强度） |
| 2.5 | LPMM 风格离线记忆整理（Dream） | 🔵 长期 | ⭐⭐⭐⭐ | 12h | 低活跃时段自动：回顾当日对话 → 日总结 / 清理过期记忆 / 更新关系 / 提取用户偏好变化 |

---

## Phase 3：情感与人格深化（MaiBot 借鉴）

| # | 任务 | 状态 | 难度 | 预计工时 | 产出 |
|---|------|------|------|----------|------|
| 3.1 | **二维情绪模型升级** | 🟡 待开始 | ⭐⭐⭐ | 8h | valence-arousal 连续空间替代 11 个离散 EmotionTag，情绪过渡更平滑 |
| 3.2 | 情绪影响回复行为 | 🟡 待开始 | ⭐⭐ | 3h | 开心→回复更长更活泼，难过→更短更温柔，影响 LLM temperature/长度/语气 |
| 3.3 | 表情/emoji 表达系统 | 🟡 待开始 | ⭐⭐ | 3h | 根据上下文自动匹配 emoji，前端 `ChatMessage` 渲染 |
| 3.4 | **talk_value 概率发言** | 🟡 待开始 | ⭐ | 2h | 低信息量消息（"嗯"、"好的"）有概率不回复，增加自然感 |

---

## Phase 4：意图路由与 Agent 编排（AstrBot 借鉴）

| # | 任务 | 状态 | 难度 | 预计工时 | 产出 |
|---|------|------|------|----------|------|
| 4.1 | **SubAgent 架构** | 🟡 待开始 | ⭐⭐⭐⭐ | 10h | intent_router 升级为 SubAgentOrchestrator：ChatAgent / TaskAgent / MemoryAgent / DeviceAgent |
| 4.2 | MCP 工具协议适配 | 🔵 长期 | ⭐⭐⭐ | 8h | `@register_action` 装饰器输出 MCP 兼容 JSON Schema，支持接入外部 MCP 服务器 |
| 4.3 | TaskAgent：复杂任务分解执行 | 🔵 长期 | ⭐⭐⭐⭐ | 12h | ReAct 循环 + 工具链调用 + 执行结果汇总 |
| 4.4 | 意图路由准确率优化 | 🟡 待开始 | ⭐⭐ | 3h | 当前依赖 LLM 分类 + 关键词回退，增加 few-shot 示例和规则权重调优 |

---

## Phase 5：多模态与交互升级

| # | 任务 | 状态 | 难度 | 预计工时 | 产出 |
|---|------|------|------|----------|------|
| 5.1 | 语音实时对话优化 | 🟡 待开始 | ⭐⭐⭐ | 6h | `voice_layer/` 延迟和流畅度优化，支持打断和语气调节 |
| 5.2 | 图片理解（多模态） | 🟡 待开始 | ⭐⭐ | 4h | 用户发送图片时调用 vision LLM 理解内容并自然回应 |
| 5.3 | Live2D 表情与情绪联动增强 | 🟡 待开始 | ⭐⭐ | 3h | 更多 motion→emotion 映射，动作过渡更平滑 |
| 5.4 | PC 客户端桌面通知 | 🟡 待开始 | ⭐⭐ | 3h | 主动消息到达时系统级通知，Electron Notification API |

---

## Phase 6：工程化与生态

| # | 任务 | 状态 | 难度 | 预计工时 | 产出 |
|---|------|------|------|----------|------|
| 6.1 | 插件系统基础：目录扫描 + 热加载 | 🔵 长期 | ⭐⭐⭐⭐ | 10h | `plugins/` 目录，watchfiles 热重载，参考 AstrBot Star 模式 |
| 6.2 | 多平台适配（QQ/Telegram/Discord） | 🔵 长期 | ⭐⭐⭐⭐ | 16h | 复用 `gateway_adapter/` 架构，参考 AstrBot 的 Platform Adapter 模式 |
| 6.3 | CI/CD：自动化测试 + Docker 镜像 | 🟡 待开始 | ⭐⭐ | 4h | GitHub Actions 跑 Python 测试，自动构建 Docker |
| 6.4 | WebUI 管理面板 | 🔵 长期 | ⭐⭐⭐⭐ | 16h | 可视化管理 LLM/语音/主动关怀配置，插件市场浏览安装 |
| 6.5 | 记忆可视化 | 🔵 长期 | ⭐⭐⭐ | 8h | 知识图谱可视化，展示小暖对用户的记忆网络 |

---

## Phase 7：安全与护栏

| # | 任务 | 状态 | 难度 | 预计工时 | 产出 |
|---|------|------|------|----------|------|
| 7.1 | 设备命令沙箱执行 | 🟡 待开始 | ⭐⭐⭐ | 6h | 参考 AstrBot Agent Sandbox，限制 shell/文件访问范围 |
| 7.2 | 内容安全过滤增强 | 🟡 待开始 | ⭐⭐ | 3h | `safety_guard/` 增加敏感话题识别和模糊处理 |
| 7.3 | 用户数据隐私控制 | 🟡 待开始 | ⭐⭐ | 3h | 记忆数据导出/删除，对话历史清除确认 |

---

## Phase 8：实时流式管线与 3D 形象（DLP3D 借鉴）

> 来源：[dlp3d-ai/dlp3d.ai](https://github.com/dlp3d-ai/dlp3d.ai)（Digital Life Project 2，SIGGRAPH Asia 2025，MIT）。
> 重点借鉴其 orchestrator 的流式工程，不引入其 3D 模型资产（示例含原神角色，仅限非商用）。

| # | 任务 | 状态 | 难度 | 预计工时 | 产出 |
|---|------|------|------|----------|------|
| 8.1 | **LLM 分段 → TTS 并行流式管线** | 🔵 设计中 | ⭐⭐⭐⭐ | 10h | 参考 DLP3D Aggregator 模式：长回复按句切段，TTS/情感分析并行起跑，首字延迟显著下降；落在 `voice_layer/` + `core_orchestrator/` 流式路径。设计稿：[docs/streaming-tts-pipeline-design.md](docs/streaming-tts-pipeline-design.md) |
| 8.2 | **打断处理与自适应缓冲** | 🟡 待开始 | ⭐⭐⭐ | 6h | 用户插话时取消在途 TTS/动作流、缓冲水位自适应；补 5.1 的"支持打断"，参考 DLP3D interruption/adaptive buffering 机制 |
| 8.3 | **Classification/Reaction 小模型独立环节** | 🟡 待开始 | ⭐⭐ | 4h | 每轮用小模型独立打标（用户意图 + 角色情绪/关系变化），结果喂给 `persona_engine` 状态机，替代主 LLM 自报情绪；与 3.1 二维情绪模型联动 |
| 8.4 | 音频/表情同步聚合器 | 🟡 待开始 | ⭐⭐⭐ | 6h | 参考 `tts_reaction_aggregator` / `blendshapes_aggregator`：TTS 音频与表情动作时间轴对齐后统一下发，强化 5.3 Live2D 唇形/表情同步 |
| 8.5 | 流式传输协议升级（Protobuf/二进制帧） | 🔵 长期 | ⭐⭐⭐ | 8h | 评估将 SSE/JSON 流升级为 DLP3D 式 Protobuf 流式结构，降低音频+动作多路流的传输开销 |
| 8.6 | 3D 形象升级路径：接入 speech2motion / audio2face | 🔵 长期 | ⭐⭐⭐⭐ | 16h | 补 `action_layer` 占位模块：将 DLP3D 的 speech2motion（语音→肢体）与 audio2face（音频→面部）作为独立微服务接入，前端可换 Three.js 3D 形象，Live2D 保留为轻量选项 |

---

## 快速启动指南（选一个开始）

### 如果只有 2 小时
→ 做 **3.4 talk_value 概率发言**（`node_generate_response` 加一个概率判断，改动最小，效果立竿见影）

### 如果有一个下午（4-6 小时）
→ 做 **2.1 Working Memory 压缩**（`memory_system/working.py` 增摘要压缩，大幅提升上下文质量）

### 如果有一天（8-10 小时）
→ 做 **1.5 HeartFlow 持续思考**（`proactive_care.py` 从定时轮询升级为 per-user 常驻任务，是主动会话能力的质变）

### 如果想做架构升级
→ 做 **4.1 SubAgent 编排**（`intent_router.py` 拆分为多个 SubAgent，打开复杂任务处理的想象力）

### 如果想做语音体验升级
→ 做 **8.1 LLM 分段 → TTS 并行流式管线**（DLP3D Aggregator 模式，首字延迟立竿见影，并为 8.2 打断处理打底）
