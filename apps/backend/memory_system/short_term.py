"""Redis-based short-term session cache for conversation context."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
import structlog

from shared_runtime.config import get_settings
from shared_runtime.lite_mode import InMemoryShortTermMemory
from shared_contracts.models import EmotionTag, MemoryEntry

logger = structlog.get_logger(__name__)

settings = get_settings()

_redis_pool: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
    return _redis_pool


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("short_term.redis_closed")


class ShortTermMemory:
    """LRU + TTL based short-term memory cache per session.

    In lite_mode falls back to an in-memory dict (no Redis required).
    """

    def __init__(self, max_entries: int = 100, default_ttl: int = 3600) -> None:
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        if settings.lite_mode:
            self._backend: Any = InMemoryShortTermMemory(max_entries=max_entries, default_ttl=default_ttl)
            self._redis = None  # type: ignore[assignment]
        else:
            self._backend = None
            self._redis = _get_redis()

    def _session_key(self, session_id: str) -> str:
        return f"companion:stm:{session_id}"

    def _turn_key(self, session_id: str, turn_id: str) -> str:
        return f"companion:stm:{session_id}:{turn_id}"

    async def add_turn(
        self,
        session_id: str,
        turn_id: str,
        user_message: str,
        assistant_message: str,
        emotion: Optional[EmotionTag] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store a conversation turn in short-term memory."""
        if settings.lite_mode:
            await self._backend.add_turn(session_id, turn_id, user_message, assistant_message, emotion, metadata)
            return
        key = self._turn_key(session_id, turn_id)
        data = {
            "turn_id": turn_id,
            "session_id": session_id,
            "user_message": user_message,
            "assistant_message": assistant_message,
            "emotion": emotion.value if emotion else None,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        pipe = self._redis.pipeline()
        pipe.setex(key, self.default_ttl, json.dumps(data, ensure_ascii=False))
        # Maintain ordered list of turn IDs per session
        pipe.lpush(self._session_key(session_id), turn_id)
        # Trim to max entries
        pipe.ltrim(self._session_key(session_id), 0, self.max_entries - 1)
        # Set TTL on session list too
        pipe.expire(self._session_key(session_id), self.default_ttl)
        await pipe.execute()
        logger.info("short_term.turn_added", session_id=session_id, turn_id=turn_id)

    async def get_session_turns(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve all turns for a session in chronological order."""
        if settings.lite_mode:
            return await self._backend.get_session_turns(session_id)
        turn_ids = await self._redis.lrange(self._session_key(session_id), 0, -1)
        turns: List[Dict[str, Any]] = []
        for turn_id in reversed(turn_ids):  # lpush means reverse order
            data = await self._redis.get(self._turn_key(session_id, turn_id))
            if data:
                turns.append(json.loads(data))
        return turns

    async def get_recent_context(
        self,
        session_id: str,
        last_n: int = 5,
    ) -> str:
        """Get recent conversation context as a formatted string."""
        if settings.lite_mode:
            return await self._backend.get_recent_context(session_id, last_n)
        turns = await self.get_session_turns(session_id)
        recent = turns[-last_n:] if turns else []
        lines = []
        for turn in recent:
            lines.append(f"User: {turn['user_message']}")
            lines.append(f"Assistant: {turn['assistant_message']}")
        return "\n".join(lines)

    async def clear_session(self, session_id: str) -> None:
        """Remove all short-term memory for a session."""
        if settings.lite_mode:
            await self._backend.clear_session(session_id)
            return
        turn_ids = await self._redis.lrange(self._session_key(session_id), 0, -1)
        if turn_ids:
            keys = [self._turn_key(session_id, tid) for tid in turn_ids]
            keys.append(self._session_key(session_id))
            await self._redis.delete(*keys)
        logger.info("short_term.session_cleared", session_id=session_id)

    async def set_user_context(self, user_id: str, context: Dict[str, Any], ttl: int = 300) -> None:
        """Store ephemeral user context (e.g., current intent, pending action)."""
        if settings.lite_mode:
            await self._backend.set_user_context(user_id, context, ttl)
            return
        key = f"companion:stm:ctx:{user_id}"
        await self._redis.setex(key, ttl, json.dumps(context, ensure_ascii=False))

    async def get_user_context(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve ephemeral user context."""
        if settings.lite_mode:
            return await self._backend.get_user_context(user_id)
        key = f"companion:stm:ctx:{user_id}"
        data = await self._redis.get(key)
        return json.loads(data) if data else None

    async def delete_user_context(self, user_id: str) -> None:
        if settings.lite_mode:
            await self._backend.delete_user_context(user_id)
            return
        key = f"companion:stm:ctx:{user_id}"
        await self._redis.delete(key)


short_term_memory = ShortTermMemory()
