# safety_guard

> 内容安全护栏 · 输入/输出双向过滤 · 第三方宿主可继承覆盖。

## 我是什么

`safety_guard` 是 V2 重构波次 6 落地的**最小护栏骨架**：

- 业务模块在调用 LLM **之前**用 `check_input` 过滤用户输入
- 在调用 LLM **之后**用 `check_output` 过滤模型回复
- 默认实现仅做关键词 blocklist（占位用），后续接入云端 moderation API

零依赖（`dataclasses` + `typing`），第三方宿主可继承 `SafetyGuard` 覆盖 `check_input` / `check_output` 接入自家审核服务。

## 暴露什么 API

```python
from safety_guard import (
    SafetyVerdict,    # @dataclass(frozen=True)
    SafetyGuard,      # 类，可继承覆盖
    default_guard,    # 进程级默认实例
)
```

`SafetyVerdict` 字段：
- `allowed: bool` — 是否放行
- `reason: str` — 拦截原因
- `matched_terms: tuple[str, ...]` — 命中的关键词

## 依赖什么

- companion-ai 内部：无
- 第三方：无（仅标准库）

## 怎么单独启

```bash
cd companion-ai
python -m safety_guard "我今天有点想自杀"
# {"allowed": false, "reason": "...", "matched": [...]}
```

## 最小用法

```python
from safety_guard import default_guard

verdict = default_guard.check_input("我今天有点想自杀")
if not verdict.allowed:
    print("blocked:", verdict.reason, verdict.matched_terms)
else:
    print("ok")
```

## 自定义 Guard

```python
from safety_guard import SafetyGuard, SafetyVerdict

class CloudModerationGuard(SafetyGuard):
    async def check_input_async(self, text: str) -> SafetyVerdict:
        # 调用自家云端 moderation API
        ...
```

## 第三方宿主接入提示

骨架版本仅有关键词过滤，**生产环境必须**继承 `SafetyGuard` 接入合规审核服务（如 Azure Content Safety / 自建分类模型）。
