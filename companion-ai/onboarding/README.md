# onboarding

> 新用户引导 · 0-1 破冰流程 · 第三方宿主可替换默认问答模板。

## 我是什么

`onboarding` 是 V2 重构波次 6 落地的**新用户引导骨架**：

- 第一次接入的新用户走 **角色选择 → 称呼 → 语言偏好 → 初始问候** 四步
- 只产出 `OnboardingResult` 数据；落库由 `core_orchestrator` 完成
- 与 `persona_engine` 解耦，只产数据不查角色库
- 第三方宿主可自定义步骤、替换默认问答模板

## 暴露什么 API

```python
from onboarding import (
    OnboardingStep,      # @dataclass(frozen=True): key / prompt / optional
    OnboardingResult,    # @dataclass: user_id / role_id / nickname / locale / completed_steps
    default_steps,       # 返回默认四步引导列表
)
```

## 依赖什么

- companion-ai 内部：无
- 第三方：无（仅标准库）

## 怎么单独启

```bash
cd companion-ai
python -m onboarding
# 打印默认四步引导
```

## 最小用法

```python
from onboarding import default_steps, OnboardingResult

steps = default_steps()
result = OnboardingResult(user_id="u1")
for step in steps:
    print(step.key, "->", step.prompt)
    result.completed_steps.append(step.key)
result.role_id = "xiaonuan"
result.nickname = "阿正"
result.locale = "zh-CN"
print(result)
```

## 自定义步骤

```python
from onboarding import OnboardingStep

custom_steps = [
    OnboardingStep(key="age_group", prompt="你的年龄段是？", optional=True),
    OnboardingStep(key="interests", prompt="你最近的兴趣是什么？", optional=False),
]
```

## 第三方宿主接入提示

骨架版本仅有数据结构与默认步骤，宿主接入主链路时需要：
1. 在 `core_orchestrator` 增加 `state == "onboarding"` 分支
2. 把 `OnboardingResult` 写入 `user_profile` 与 `persona_engine` 关系表
3. 前端给四步配交互组件
