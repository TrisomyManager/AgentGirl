"""Platform adapters for gateway_adapter."""

from .base import BasePlatformAdapter
from .telegram import TelegramAdapter
from .discord import DiscordAdapter
from .wechat import WeChatAdapter
from .app_ws import AppWebSocketAdapter

__all__ = [
    "BasePlatformAdapter",
    "TelegramAdapter",
    "DiscordAdapter",
    "WeChatAdapter",
    "AppWebSocketAdapter",
]
