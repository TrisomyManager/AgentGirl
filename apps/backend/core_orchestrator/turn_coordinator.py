"""Cancellation-safe per-user/session ordering without retaining idle locks."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from shared_runtime.user_lifecycle import user_operation


@dataclass
class _Entry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class TurnCoordinator:
    def __init__(self):
        self._entries: dict[tuple[str, str], _Entry] = {}

    @asynccontextmanager
    async def hold(self, user_id: str, session_id: str):
        key = (user_id, session_id)
        entry = self._entries.setdefault(key, _Entry())
        entry.users += 1
        try:
            async with user_operation(user_id), entry.lock:
                yield
        finally:
            entry.users -= 1
            if not entry.users and self._entries.get(key) is entry:
                del self._entries[key]
