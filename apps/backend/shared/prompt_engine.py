"""[Deprecated] ``shared.prompt_engine`` 已物理搬迁至 ``shared_runtime.prompt_engine``.

P1-F (V2.2) 起, 本文件仅做 re-export shim. 新代码请直接::

    from shared_runtime.prompt_engine import build_base_system_prompt, build_conversation_system_prompt
"""

from __future__ import annotations

from shared_runtime.prompt_engine import (  # noqa: F401
    build_base_system_prompt,
    build_conversation_system_prompt,
)

__all__ = [
    "build_base_system_prompt",
    "build_conversation_system_prompt",
]
