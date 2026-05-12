"""[Deprecated] ``shared.llm_client`` 已物理搬迁至 ``shared_runtime.llm_client``.

P1-E (V2.1) 起, 本文件仅做 re-export shim. 新代码请直接 ``from shared_runtime
import LLMClient, chunk_text_stream, ...``; 业务模块按 ADR-006 应通过
``LLMClientProtocol`` 注入而非直接导入实现.
"""

from __future__ import annotations

from shared_runtime.llm_client import (  # noqa: F401
    LLMClient,
    _ANTHROPIC_DEFAULT_BASE,
    _CONFIG_FILE,
    _DEFAULT_TIMEOUT,
    _NEGATIVE_HINTS,
    _OPENAI_DEFAULT_BASE,
    _POSITIVE_HINTS,
    _normalize_anthropic_messages_base,
    _normalize_openai_chat_base,
    _runtime_llm_config,
    chunk_text_stream,
    format_upstream_error_text,
    get_runtime_llm_config,
    load_llm_config_from_disk,
    save_llm_config_to_disk,
    update_runtime_llm_config,
)

__all__ = [
    "LLMClient",
    "chunk_text_stream",
    "format_upstream_error_text",
    "get_runtime_llm_config",
    "update_runtime_llm_config",
    "save_llm_config_to_disk",
    "load_llm_config_from_disk",
]
