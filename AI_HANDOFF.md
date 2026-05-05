# AI 工程交接文档

> 写给下一位接手本工程的 AI，或者下一轮对话里的自己。  
> 更新日期：2026-05-04

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
- `companion-ai/core_orchestrator/project_status.py`
  - 目前是“项目当前实现状态”的最准入口之一，前端状态页直接消费它。

### 还没真正收口的部分

- `memory_system`
  - 仍偏“长期记忆仓库”，working memory / persistent memory 分层尚未完成。
- `state_machine.py` / Prompt 体系
  - system prompt 仍需要从硬编码抽到共享层，便于人格文件、关系摘要、调试台复用。
- 主聊天文本流式输出
  - 语音通话链路已经流式，主聊天消息区还没有真正接上 token streaming。
- `action_layer` / `device_coordination`
  - 产品闭环仍未完成，更多是架子和边界预留。

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

### 2026-05-04 的实际验证结果

- `python -m pytest -q`
  - **89 passed / 7 failed**
- 失败主要分两类
  - `memory_system/tests/test_memory.py`
    - SQLite 环境下向量字段插入参数绑定数量不匹配
  - `voice_layer/tests/test_voice.py`
    - 当前机器缺少 `ffmpeg`，导致音频时长、转码、转写相关测试失败

所以不要再把“93 passed”当成当前真实基线。

---

## 6. 下一步推荐动作

优先级建议如下：

1. **先修 Prompt Engine 收敛**
   - 目标：把 `state_machine.py` 内的 system prompt 硬编码抽到共享层。
2. **再修记忆系统测试与模型分层**
   - 目标：先把 sqlite 测试跑稳，再推进 working / persistent memory 分层。
3. **补主聊天流式输出**
   - 目标：让主聊天 UI 和实时语音通话在“流式体验”上不再分裂。
4. **最后考虑主动能力**
   - 目标：等前 3 项稳定后，再认真推进 `action_layer` / `device_coordination`。

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
