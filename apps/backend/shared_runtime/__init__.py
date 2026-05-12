"""shared_runtime —— 宿主可注入的运行时层.

职责:
- 提供 LLM 客户端 / 配置加载 / Lite Mode / 数据库连接 等"运行时副作用"实现
- 业务模块统一通过本包获取依赖, 第三方宿主可整体替换实现
- 与 ``shared_contracts`` 分层: 契约层零依赖纯模型, 运行时层有副作用

P1-E 物理搬迁完成 (V2.1):
- ``config`` / ``lite_mode`` / ``llm_client`` / ``database`` /
  ``voice_runtime_config`` 全部物理位于本包
- ``shared/`` 目录下同名文件已转为 deprecated re-export shim, 仅做兼容
- 业务侧应优先 ``from shared_runtime import get_settings, LLMClient, ...``

ADR-006 硬约束 2 兜底实现:
- ``LLMClient`` 已具备 ``generate`` / ``generate_stream`` 方法,
  与 ``shared_contracts.protocols.LLMClient`` Protocol 形状对齐
- 第三方宿主可注入自家实现替换
"""

from __future__ import annotations

import os

# --- 配置 (物理位于 shared_runtime.config) ---
from .config import Settings, get_settings

# --- Lite Mode (物理位于 shared_runtime.lite_mode) ---
from .lite_mode import EventHandler, InMemoryEventBus, InMemoryShortTermMemory

# --- LLM 客户端 (物理位于 shared_runtime.llm_client) ---
from .llm_client import (
    LLMClient,
    chunk_text_stream,
    format_upstream_error_text,
    get_runtime_llm_config,
    load_llm_config_from_disk,
    save_llm_config_to_disk,
    update_runtime_llm_config,
)

# --- 语音运行时配置 (物理位于 shared_runtime.voice_runtime_config) ---
from .voice_runtime_config import (
    clear_runtime_voice_config,
    get_runtime_voice_config,
    load_voice_config_from_disk,
    save_voice_config_to_disk,
    update_runtime_voice_config,
    voice_config_file_path,
)

# --- 数据库 (物理位于 shared_runtime.database) ---
from .database import (
    AsyncSessionLocal,
    Base,
    close_database,
    engine,
    get_db,
    get_db_session,
    init_database_schema,
)


def is_lite_mode() -> bool:
    """是否处于 Lite Mode (无 Docker 依赖, 使用 SQLite + 内存替代)."""
    return os.getenv("COMPANION_LITE_MODE", "").lower() in {"1", "true", "yes", "on"}


__all__ = [
    # 配置
    "Settings",
    "get_settings",
    # Lite Mode
    "EventHandler",
    "InMemoryEventBus",
    "InMemoryShortTermMemory",
    "is_lite_mode",
    # LLM
    "LLMClient",
    "chunk_text_stream",
    "format_upstream_error_text",
    "get_runtime_llm_config",
    "update_runtime_llm_config",
    "save_llm_config_to_disk",
    "load_llm_config_from_disk",
    # 语音运行时
    "get_runtime_voice_config",
    "update_runtime_voice_config",
    "save_voice_config_to_disk",
    "load_voice_config_from_disk",
    "clear_runtime_voice_config",
    "voice_config_file_path",
    # 数据库
    "AsyncSessionLocal",
    "Base",
    "engine",
    "get_db",
    "get_db_session",
    "close_database",
    "init_database_schema",
]
