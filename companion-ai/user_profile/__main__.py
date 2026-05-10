"""`python -m user_profile` — minimal smoke demo of InMemoryUserProfileStore."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from user_profile import InMemoryUserProfileStore, UserProfileSnapshot


async def _demo() -> None:
    store = InMemoryUserProfileStore()
    await store.upsert(UserProfileSnapshot(user_id="demo", display_name="Demo"))
    await store.merge_preferences("demo", theme="dark", language="zh-CN")
    snapshot = await store.get("demo")
    print(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2))


def main() -> None:
    asyncio.run(_demo())


if __name__ == "__main__":
    main()
