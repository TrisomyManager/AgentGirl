"""Private host configuration. Incoming payloads can never grant an identity."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator

from shared_contracts import PlatformMessage


class PlatformConfigError(ValueError):
    pass


class HostModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Account(HostModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    platform: Literal["telegram", "discord", "qq"]
    enabled: bool = False
    receive: bool = False
    reply: bool = False
    token: SecretStr | None = Field(default=None, repr=False)
    app_id: str | None = Field(default=None, pattern=r"^[0-9]{1,32}$")
    secret: SecretStr | None = Field(default=None, repr=False)
    message_content: bool = False

    @model_validator(mode="after")
    def credentials(self):
        if self.enabled and self.receive:
            if self.platform == "qq":
                if not self.app_id or not self.secret or not self.secret.get_secret_value():
                    raise ValueError("QQ credentials missing")
            elif not self.token or not self.token.get_secret_value():
                raise ValueError("Bot credential missing")
        for value in (self.token, self.secret):
            if value and (
                not 1 <= len(value.get_secret_value()) <= 512
                or any(ord(char) < 33 or ord(char) > 126 for char in value.get_secret_value())
            ):
                raise ValueError("Invalid credential")
        if self.token and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,512}", self.token.get_secret_value()):
            raise ValueError("Invalid bot token")
        return self

    def fingerprint(self):
        values = self.model_dump(exclude={"token", "secret"})
        values.update(
            token=self.token.get_secret_value() if self.token else "",
            secret=self.secret.get_secret_value() if self.secret else "",
        )
        return _digest(values)

    def identity_key(self):
        # An alias represents one bot for its lifetime. Credential rotation and
        # enable/disable must not replay old messages or bypass erasure receipts.
        return _digest([self.id, self.platform, self.app_id])


class Binding(HostModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    account_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=128)
    audience: Literal["private", "room"]
    thread_id: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool = False

    @field_validator("user_id", "actor_id", "conversation_id", "thread_id")
    @classmethod
    def identifiers(cls, value):
        if value is not None and (value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError("Invalid identifier")
        return value

    def matches(self, message: PlatformMessage):
        return self.enabled and (
            self.account_id,
            self.actor_id,
            self.conversation_id,
            self.audience,
            self.thread_id,
        ) == (message.account_id, message.actor_id, message.conversation_id, message.audience, message.thread_id)


class PlatformsConfig(HostModel):
    version: Literal[1] = 1
    enabled: bool = False
    accounts: tuple[Account, ...] = ()
    bindings: tuple[Binding, ...] = ()
    # A separate loopback listener, sharing the host's cancellation and privacy barrier.
    qq_callback_port: int | None = Field(default=None, ge=1024, le=65535)

    @model_validator(mode="after")
    def unique_bindings(self):
        if len(self.accounts) > 16 or len(self.bindings) > 1000:
            raise ValueError("Too many platform bindings")
        account_ids = [account.id for account in self.accounts]
        if len(set(account_ids)) != len(account_ids) or len({b.id for b in self.bindings}) != len(self.bindings):
            raise ValueError("Duplicate platform identifier")
        targets = set()
        for binding in self.bindings:
            key = (binding.account_id, binding.actor_id, binding.conversation_id, binding.audience, binding.thread_id)
            if binding.account_id not in account_ids or key in targets:
                raise ValueError("Invalid or duplicate platform target")
            targets.add(key)
        if (
            self.enabled
            and self.qq_callback_port is None
            and any(a.enabled and a.receive and a.platform == "qq" for a in self.accounts)
        ):
            raise ValueError("QQ callback listener is required")
        return self

    def resolve(self, message):
        if not self.enabled or message.forwarded or (message.audience == "room" and not message.mentions_bot):
            return None
        account = self.account(message.account_id)
        if not account or not account.enabled or not account.receive or account.platform != message.platform.value:
            return None
        for binding in self.bindings:
            if binding.matches(message):
                return account, binding, binding_fingerprint(account, binding)
        return None

    def account(self, account_id):
        return next((account for account in self.accounts if account.id == account_id), None)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def binding_fingerprint(account, binding):
    return _digest([account.identity_key(), binding.model_dump(exclude={"enabled"})])


class ConfigSource:
    def __init__(self, path=None):
        self.path = Path(path).absolute() if path is not None else None

    @classmethod
    def from_environment(cls):
        value = os.environ.get("COMPANION_PLATFORMS_CONFIG_FILE")
        if not value:
            return cls()
        path = Path(value)
        return cls(path if path.is_absolute() else Path(__file__).resolve().parents[1] / path)

    def load(self):
        if self.path is None:
            return PlatformsConfig()
        try:
            # A bounded read also covers a file replaced or enlarged between stat and open.
            if self.path.is_symlink() or any(parent.is_symlink() for parent in self.path.parents):
                raise PlatformConfigError("Platform configuration must be a private regular file")
            with self.path.open("rb") as source:
                data = source.read(256 * 1024 + 1)
            if len(data) > 256 * 1024:
                raise PlatformConfigError("Platform configuration exceeds its size limit")
            # JSON input permits arrays for immutable tuple fields; strict scalar types remain enforced.
            return PlatformsConfig.model_validate_json(data)
        except (OSError, ValidationError, UnicodeError, ValueError):
            # Pydantic validation text can include plaintext credentials. Never return it.
            raise PlatformConfigError("Platform configuration is unavailable or invalid") from None
