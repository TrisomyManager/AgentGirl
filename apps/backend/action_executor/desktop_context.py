"""Consent-based desktop metadata gates. No screen pixels, titles or file contents.

The server measures dwell time itself and keeps observations for at most 45s.
Busy/locked/fullscreen observations on any fresh device suppress interruptions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import JSON, Column, String

from shared_runtime.database import AsyncSessionLocal, Base


class ProactivePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    desktop_enabled: bool = False
    allowed_apps: list[str] = Field(default_factory=list, max_length=32)
    dwell_seconds: int = Field(default=45, ge=15, le=3600)
    min_idle_seconds: int = Field(default=0, ge=0, le=3600)

    @field_validator("allowed_apps")
    @classmethod
    def normalize_apps(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 128 or "/" in item or "\\" in item for item in value):
            raise ValueError("请填写应用进程名，不要填写路径")
        return list(dict.fromkeys(item.strip().casefold() for item in value))


class DesktopObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=64)
    device_id: str = Field(min_length=1, max_length=128)
    foreground_app: str = Field(default="", max_length=128)
    idle_seconds: float = Field(default=0, ge=0, le=86400)
    busy: bool = False
    interacting: bool = False
    fullscreen: bool = False
    locked: bool = False


@dataclass(frozen=True)
class ContextDecision:
    allowed: bool
    reason: str
    signature: tuple | None = None
    foreground_app: str = ""


class DesktopContextGate:
    ttl = 45.0

    def __init__(self) -> None:
        self._observations: dict[tuple[str, str], tuple[DesktopObservation, float, float]] = {}
        self._delivered: dict[str, tuple] = {}

    def update(self, observation: DesktopObservation, *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        # Bounded by live observations, not by the number of users ever seen.
        self._observations = {key: value for key, value in self._observations.items() if now - value[1] <= self.ttl}
        key = observation.user_id, observation.device_id
        old = self._observations.get(key)
        app = observation.foreground_app.strip().casefold()
        since = old[2] if old and old[0].foreground_app == app and now - old[1] <= self.ttl else now
        self._observations[key] = observation.model_copy(update={"foreground_app": app}), now, since
        if len(self._observations) > 4096:
            oldest = min(self._observations, key=lambda item: self._observations[item][1])
            self._observations.pop(oldest, None)
        active_users = {key[0] for key in self._observations}
        self._delivered = {uid: value for uid, value in self._delivered.items() if uid in active_users}

    def evaluate(self, user_id: str, policy: ProactivePolicy, *, now: float | None = None) -> ContextDecision:
        now = time.monotonic() if now is None else now
        if not policy.enabled:
            return ContextDecision(False, "disabled")
        if not policy.desktop_enabled:
            return ContextDecision(False, "desktop_disabled")
        observations = [value for (uid, _), value in self._observations.items() if uid == user_id]
        if not observations:
            return ContextDecision(False, "no_context")
        fresh = [value for value in observations if now - value[1] <= self.ttl]
        if not fresh:
            return ContextDecision(False, "stale")
        for observation, _, _ in fresh:
            for flag in ("locked", "fullscreen", "busy", "interacting"):
                if getattr(observation, flag):
                    return ContextDecision(False, flag)
        observation, _, since = max(fresh, key=lambda item: item[1])
        if observation.foreground_app not in policy.allowed_apps:
            return ContextDecision(False, "not_allowlisted")
        if now - since < policy.dwell_seconds:
            return ContextDecision(False, "dwelling")
        if observation.idle_seconds < policy.min_idle_seconds:
            return ContextDecision(False, "not_idle")
        signature = observation.device_id, observation.foreground_app, since
        if self._delivered.get(user_id) == signature:
            return ContextDecision(False, "already_delivered")
        return ContextDecision(True, "ready", signature, observation.foreground_app)

    def clear(self, user_id: str) -> None:
        self._observations = {key: value for key, value in self._observations.items() if key[0] != user_id}
        self._delivered.pop(user_id, None)

    def user_ids(self) -> list[str]:
        now = time.monotonic()
        return sorted({uid for (uid, _), value in self._observations.items() if now - value[1] <= self.ttl})

    def mark_delivered(self, user_id: str, signature: tuple | None) -> None:
        if signature is not None:
            self._delivered[user_id] = signature


class ProactivePreferencesORM(Base):
    __tablename__ = "proactive_preferences"
    user_id = Column(String(64), primary_key=True)
    policy_json = Column(JSON, nullable=False)


async def read_policy(user_id: str) -> ProactivePolicy:
    async with AsyncSessionLocal() as session:
        row = await session.get(ProactivePreferencesORM, user_id)
        return ProactivePolicy.model_validate(row.policy_json) if row else ProactivePolicy()


async def write_policy(user_id: str, policy: ProactivePolicy) -> None:
    async with AsyncSessionLocal() as session:
        await session.merge(ProactivePreferencesORM(user_id=user_id, policy_json=policy.model_dump()))
        await session.commit()
