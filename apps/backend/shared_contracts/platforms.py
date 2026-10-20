"""Normalized external messages deliberately contain no trusted internal owner."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared_contracts.models import Platform


class PlatformMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    platform: Platform
    account_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=256)
    message_id: str = Field(min_length=1, max_length=256)
    actor_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=16000)
    audience: Literal["private", "room"]
    thread_id: str | None = Field(default=None, max_length=128)
    mentions_bot: bool = False
    forwarded: bool = False
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("account_id", "event_id", "message_id", "actor_id", "conversation_id", "thread_id")
    @classmethod
    def identifiers(cls, value):
        if value is not None and any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Platform identifiers cannot contain control characters")
        return value
