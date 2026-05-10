# examples/integration_minimal

> 最小可运行集成 Demo · 证明「模块独立可拆」。

本目录是 **P1-A 的硬证据**：在**不引入** `core_orchestrator`、**不启动** FastAPI、**不依赖** Docker 的前提下，仅组合三个独立模块就能跑出端到端的对话片段。

## 用了哪些模块

| 模块 | 来源 | 作用 |
|---|---|---|
| `shared_contracts` | V2 波次 1 契约层 | EmotionState / EmotionTag 数据契约 |
| `persona_engine.persona_store` | V2 波次 4 多角色 | 加载「小暖」`PersonaProfile` |
| `persona_engine.tone_generator` | persona_engine | 根据情绪 + 关系生成语气片段 |
| `safety_guard` | V2 波次 6 骨架 | 用户输入护栏 + 模型输出护栏 |
| `user_profile` | V2 波次 6 骨架 | 跨对话用户画像 |
| `onboarding` | V2 波次 6 骨架 | 新用户 4 步引导 |

**没有用**：core_orchestrator、memory_system（依赖外部 LLM/embedding）、voice_layer（依赖 ASR/TTS API key）、action_executor、FastAPI、Docker、PostgreSQL、Redis、Neo4j。

## 怎么跑

```bash
cd companion-ai
python examples/integration_minimal/run.py
```

或：

```bash
cd companion-ai/examples/integration_minimal
python run.py
```

## 期望产出

- 走完 4 步 onboarding 拿到 `OnboardingResult`
- 把用户偏好写入 `InMemoryUserProfileStore`
- 加载「小暖」`PersonaProfile`，构造一个 `EmotionState`
- 用 `ToneGenerator` 生成系统提示词的语气片段
- 模拟用户输入 → 经 `safety_guard.check_input` → 拼接 system prompt → 经 `safety_guard.check_output` 输出回复
- 全程 zero LLM call、zero network、zero database

## 第三方宿主接入提示

把这个 demo 的 `run.py` 对照到自家工程：
- `LLMClient` 处替换为你自家 LLM 调用
- `InMemoryUserProfileStore` 替换为持久化实现
- `safety_guard.SafetyGuard` 继承覆盖接入云端审核
- `persona_engine.persona_store` 用自家 YAML 替换

即可在自家工程独立运行陪伴 AI 能力，无需引入本仓库的 `core_orchestrator`。
