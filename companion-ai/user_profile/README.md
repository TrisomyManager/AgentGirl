# user_profile

> 跨对话用户画像 · 偏好 / 性格 / 兴趣 · Protocol + 内存版骨架。

## 我是什么

`user_profile` 是 V2 重构波次 6 落地的**用户画像骨架**：

- 维护**稳定属性**（偏好、性格、兴趣、关键事件）
- 与 `memory_system` 分工：**memory** 侧重事件与关系图，**user_profile** 侧重稳定属性
- 当前提供 `UserProfileStore` Protocol + `InMemoryUserProfileStore` 实现，第三方宿主可注入持久化版本

## 暴露什么 API

```python
from user_profile import (
    UserProfileSnapshot,        # @dataclass
    UserProfileStore,           # Protocol（异步接口）
    InMemoryUserProfileStore,   # Demo / 单测用
)
```

`UserProfileSnapshot` 字段：
- `user_id: str`
- `display_name: str | None`
- `locale: str | None`
- `preferences: dict[str, Any]`
- `traits: dict[str, Any]`
- `metadata: dict[str, Any]`

`UserProfileStore` Protocol：
- `async get(user_id) -> UserProfileSnapshot | None`
- `async upsert(snapshot) -> None`
- `async merge_preferences(user_id, **kwargs) -> None`

## 依赖什么

- companion-ai 内部：无
- 第三方：无（仅标准库）

## 怎么单独启

```bash
cd companion-ai
python -m user_profile
# 跑一个 demo：upsert + get
```

## 最小用法

```python
import asyncio
from user_profile import InMemoryUserProfileStore, UserProfileSnapshot

async def demo():
    store = InMemoryUserProfileStore()
    await store.upsert(UserProfileSnapshot(user_id="u1", display_name="Alex"))
    await store.merge_preferences("u1", theme="dark", language="zh-CN")
    print(await store.get("u1"))

asyncio.run(demo())
```

## 自定义持久化 Store

```python
from user_profile import UserProfileStore, UserProfileSnapshot

class SqliteUserProfileStore:
    async def get(self, user_id: str) -> UserProfileSnapshot | None: ...
    async def upsert(self, snapshot: UserProfileSnapshot) -> None: ...
    async def merge_preferences(self, user_id: str, **kwargs) -> None: ...

# 由于是 Protocol，无需继承基类，duck typing 即可
store: UserProfileStore = SqliteUserProfileStore()
```

## 第三方宿主接入提示

骨架版本只提供进程内实现，**生产环境必须**注入 SQLite/PG 持久化实现（实现 Protocol 三个方法即可）。
