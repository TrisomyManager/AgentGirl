"""In-memory command + audit stores for Lite Mode / tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import DeviceAuditStore, DeviceCommandStore

_TERMINAL = frozenset({"succeeded", "failed", "denied", "timeout", "cancelled"})


class MemoryDeviceCommandStore(DeviceCommandStore):
    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create(self, command: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            cid = command["command_id"]
            self._data[cid] = dict(command)
            return dict(self._data[cid])

    async def get(self, command_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            row = self._data.get(command_id)
            return dict(row) if row else None

    async def update(self, command_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with self._lock:
            row = self._data.get(command_id)
            if row is None:
                return None
            row = dict(row)
            row.update(patch)
            row["updated_at"] = datetime.utcnow().isoformat()
            self._data[command_id] = row
            return dict(row)

    async def list_for_user(self, user_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        async with self._lock:
            rows = [dict(c) for c in self._data.values() if c.get("user_id") == user_id]
        rows.sort(key=lambda c: c.get("created_at") or "", reverse=True)
        return rows[:limit]

    async def list_non_terminal(self) -> List[Dict[str, Any]]:
        async with self._lock:
            return [dict(c) for c in self._data.values() if c.get("status") not in _TERMINAL]

    async def find_next_delivered(self, device_id: str) -> Optional[Dict[str, Any]]:
        now = datetime.utcnow()
        async with self._lock:
            candidates = [
                dict(c)
                for c in self._data.values()
                if c.get("device_id") == device_id
                and c.get("status") == "delivered"
            ]
        if not candidates:
            return None

        def _expires_at(c: Dict[str, Any]) -> Optional[datetime]:
            raw = c.get("expires_at")
            if not raw:
                return None
            try:
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                return None

        alive: List[Dict[str, Any]] = []
        for c in candidates:
            exp = _expires_at(c)
            if exp is not None and exp.tzinfo:
                exp = exp.replace(tzinfo=None)  # noqa: DTZ007 — compare naive UTC
            if exp is not None and now > exp:
                continue
            alive.append(c)
        if not alive:
            return None
        alive.sort(key=lambda c: c.get("created_at") or "")
        return alive[0]


class MemoryDeviceAuditStore(DeviceAuditStore):
    """Ring buffer of recent audit rows (default cap 100)."""

    def __init__(self, max_entries: int = 100) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._max = max_entries
        self._lock = asyncio.Lock()

    async def append(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        row = dict(entry)
        if "audit_id" not in row:
            row["audit_id"] = uuid.uuid4().hex
        if "timestamp" not in row:
            row["timestamp"] = datetime.utcnow().isoformat()
        async with self._lock:
            self._entries.append(row)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max :]
        return dict(row)

    async def list_for_scope(
        self,
        *,
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        async with self._lock:
            rows = list(self._entries)
        if user_id:
            rows = [r for r in rows if r.get("user_id") == user_id]
        if device_id:
            rows = [r for r in rows if r.get("device_id") == device_id]
        rows.reverse()
        return rows[:limit]
