"""Session mapping between platform sessions and companion sessions."""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

import structlog

from shared.models import Platform

logger = structlog.get_logger(__name__)


class SessionInfo:
    """A single active session on a platform."""

    def __init__(
        self,
        user_id: str,
        platform: Platform,
        platform_session_id: str,
        companion_session_id: Optional[str] = None,
    ) -> None:
        self.user_id = user_id
        self.platform = platform
        self.platform_session_id = platform_session_id
        self.companion_session_id = companion_session_id or str(uuid.uuid4())


class SessionManager:
    """Maps platform-specific sessions to unified companion sessions.

    Guarantees session continuity: the same user_id across platforms
    shares the same companion_session_id.
    """

    def __init__(self) -> None:
        # (user_id, platform, platform_session_id) -> SessionInfo
        self._sessions: Dict[tuple[str, Platform, str], SessionInfo] = {}
        # user_id -> companion_session_id
        self._user_sessions: Dict[str, str] = {}

    def get_or_create(
        self,
        user_id: str,
        platform: Platform,
        platform_session_id: str,
    ) -> SessionInfo:
        key = (user_id, platform, platform_session_id)
        existing = self._sessions.get(key)
        if existing:
            return existing

        companion_session_id = self._user_sessions.get(user_id)
        session = SessionInfo(
            user_id=user_id,
            platform=platform,
            platform_session_id=platform_session_id,
            companion_session_id=companion_session_id,
        )
        if companion_session_id is None:
            self._user_sessions[user_id] = session.companion_session_id
        self._sessions[key] = session
        logger.info(
            "session.created",
            user_id=user_id,
            platform=platform.value,
            companion_session_id=session.companion_session_id,
        )
        return session

    def get(self, user_id: str, platform: Platform, platform_session_id: str) -> Optional[SessionInfo]:
        return self._sessions.get((user_id, platform, platform_session_id))

    def get_companion_session(self, user_id: str) -> Optional[str]:
        return self._user_sessions.get(user_id)

    def list_for_user(self, user_id: str) -> List[SessionInfo]:
        return [s for s in self._sessions.values() if s.user_id == user_id]

    def remove(self, user_id: str, platform: Platform, platform_session_id: str) -> None:
        key = (user_id, platform, platform_session_id)
        removed = self._sessions.pop(key, None)
        if removed:
            logger.info("session.removed", user_id=user_id, platform=platform.value)
        # Keep user session mapping alive for continuity

    def remove_all_for_user(self, user_id: str) -> None:
        keys = [k for k in self._sessions if k[0] == user_id]
        for k in keys:
            self._sessions.pop(k, None)
        self._user_sessions.pop(user_id, None)
        logger.info("session.removed_all", user_id=user_id, count=len(keys))
