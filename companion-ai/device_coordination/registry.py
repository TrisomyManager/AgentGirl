"""Device registry with in-memory cache and PostgreSQL persistence."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncpg
import structlog

import shared.models
from shared.models import DeviceInfo, DeviceType
from shared.config import get_settings

logger = structlog.get_logger(__name__)

HEARTBEAT_TIMEOUT_SECONDS = 60

# In-memory cache: device_id -> DeviceInfo
_memory_cache: Dict[str, DeviceInfo] = {}
_cache_lock = asyncio.Lock()


class DeviceRegistry:
    """Manages device registration, heartbeats, and capability queries."""

    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None
        self._cleanup_task: Optional[asyncio.Task[None]] = None

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is None or self._pool._closed:  # type: ignore[attr-defined]
            settings = get_settings()
            self._pool = await asyncpg.create_pool(settings.postgres_url, min_size=2, max_size=10)
            await self._init_schema()
        return self._pool

    async def _init_schema(self) -> None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    device_name TEXT NOT NULL DEFAULT '',
                    platform TEXT NOT NULL,
                    capabilities TEXT[] DEFAULT '{}',
                    is_online BOOLEAN DEFAULT TRUE,
                    last_heartbeat TIMESTAMPTZ DEFAULT NOW(),
                    ip_address TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_devices_user_id ON devices(user_id);
                CREATE INDEX IF NOT EXISTS idx_devices_online ON devices(is_online);
                """
            )

    async def start(self) -> None:
        await self._ensure_pool()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("device_registry.started")

    async def stop(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._pool:
            await self._pool.close()
            self._pool = None
        logger.info("device_registry.stopped")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def register(self, device: DeviceInfo) -> DeviceInfo:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO devices (device_id, user_id, device_type, device_name, platform, capabilities,
                                     is_online, last_heartbeat, ip_address, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (device_id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    device_type = EXCLUDED.device_type,
                    device_name = EXCLUDED.device_name,
                    platform = EXCLUDED.platform,
                    capabilities = EXCLUDED.capabilities,
                    is_online = EXCLUDED.is_online,
                    last_heartbeat = EXCLUDED.last_heartbeat,
                    ip_address = EXCLUDED.ip_address,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                device.device_id,
                device.user_id,
                device.device_type.value,
                device.device_name,
                device.platform.value,
                device.capabilities,
                device.is_online,
                device.last_heartbeat,
                device.ip_address,
                device.metadata,
            )
        updated = _row_to_device(row)
        async with _cache_lock:
            _memory_cache[device.device_id] = updated
        logger.info("device.registered", device_id=device.device_id, user_id=device.user_id)
        return updated

    async def heartbeat(self, device_id: str, ip_address: Optional[str] = None) -> Optional[DeviceInfo]:
        pool = await self._ensure_pool()
        now = datetime.utcnow()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE devices
                SET is_online = TRUE, last_heartbeat = $1, ip_address = COALESCE($2, ip_address), updated_at = NOW()
                WHERE device_id = $3
                RETURNING *
                """,
                now,
                ip_address,
                device_id,
            )
        if row is None:
            logger.warning("device.heartbeat_unknown_device", device_id=device_id)
            return None
        device = _row_to_device(row)
        async with _cache_lock:
            _memory_cache[device_id] = device
        return device

    async def get(self, device_id: str) -> Optional[DeviceInfo]:
        async with _cache_lock:
            cached = _memory_cache.get(device_id)
            if cached and cached.is_online and (datetime.utcnow() - cached.last_heartbeat).total_seconds() < HEARTBEAT_TIMEOUT_SECONDS:
                return cached

        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM devices WHERE device_id = $1", device_id)
        if row is None:
            return None
        device = _row_to_device(row)
        async with _cache_lock:
            _memory_cache[device_id] = device
        return device

    async def list_for_user(self, user_id: str, online_only: bool = False) -> List[DeviceInfo]:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            if online_only:
                rows = await conn.fetch(
                    "SELECT * FROM devices WHERE user_id = $1 AND is_online = TRUE", user_id
                )
            else:
                rows = await conn.fetch("SELECT * FROM devices WHERE user_id = $1", user_id)
        devices = [_row_to_device(r) for r in rows]
        async with _cache_lock:
            for d in devices:
                _memory_cache[d.device_id] = d
        return devices

    async def set_offline(self, device_id: str) -> None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE devices SET is_online = FALSE, updated_at = NOW() WHERE device_id = $1",
                device_id,
            )
        async with _cache_lock:
            if device_id in _memory_cache:
                _memory_cache[device_id] = _memory_cache[device_id].model_copy(update={"is_online": False})
        logger.info("device.marked_offline", device_id=device_id)

    async def unregister(self, device_id: str) -> None:
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM devices WHERE device_id = $1", device_id)
        async with _cache_lock:
            _memory_cache.pop(device_id, None)
        logger.info("device.unregistered", device_id=device_id)

    # ------------------------------------------------------------------
    # Capability queries
    # ------------------------------------------------------------------

    async def find_by_capability(self, user_id: str, capability: str) -> List[DeviceInfo]:
        devices = await self.list_for_user(user_id, online_only=True)
        return [d for d in devices if capability in d.capabilities]

    async def find_best_for_task(self, user_id: str, required_capabilities: List[str]) -> Optional[DeviceInfo]:
        devices = await self.list_for_user(user_id, online_only=True)
        scored: List[tuple[int, DeviceInfo]] = []
        for d in devices:
            score = sum(1 for cap in required_capabilities if cap in d.capabilities)
            if score:
                scored.append((score, d))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    # ------------------------------------------------------------------
    # Background cleanup
    # ------------------------------------------------------------------

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(15)
                await self._mark_stale_offline()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("device.cleanup_loop_error")

    async def _mark_stale_offline(self) -> None:
        cutoff = datetime.utcnow() - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE devices
                SET is_online = FALSE, updated_at = NOW()
                WHERE is_online = TRUE AND last_heartbeat < $1
                RETURNING device_id
                """,
                cutoff,
            )
        for row in rows:
            device_id = row["device_id"]
            async with _cache_lock:
                if device_id in _memory_cache:
                    _memory_cache[device_id] = _memory_cache[device_id].model_copy(update={"is_online": False})
            logger.info("device.auto_offline", device_id=device_id)


def _row_to_device(row: asyncpg.Record) -> DeviceInfo:
    return DeviceInfo(
        device_id=row["device_id"],
        user_id=row["user_id"],
        device_type=DeviceType(row["device_type"]),
        device_name=row["device_name"] if "device_name" in row and row["device_name"] else row["device_id"],
        platform=shared.models.Platform(row["platform"]),
        capabilities=list(row["capabilities"]) if row["capabilities"] else [],
        is_online=row["is_online"],
        last_heartbeat=row["last_heartbeat"],
        ip_address=row["ip_address"],
        metadata=dict(row["metadata"]) if row["metadata"] else {},
    )
