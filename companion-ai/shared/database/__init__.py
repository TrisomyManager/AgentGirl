"""[Deprecated] ``shared.database`` 已物理搬迁至 ``shared_runtime.database``.

P1-E (V2.1) 起, 本文件仅做 re-export shim.
新代码请使用 ``from shared_runtime.database import Base, engine, get_db_session, ...``
或直接 ``from shared_runtime import Base, AsyncSessionLocal, ...``.

注意: ``Base.metadata`` 是单例对象, ORM 模型必须仍然 ``from shared_runtime.database
import Base`` 才能注册到同一个 metadata; 但通过本 shim 重新导出的 ``Base`` 也指向
同一个对象, 因此遗留代码 ``from shared.database import Base`` 仍然安全.
"""

from __future__ import annotations

from shared_runtime.database import (  # noqa: F401
    AsyncSessionLocal,
    Base,
    _ensure_reminder_repeat_column,
    close_database,
    engine,
    get_db,
    get_db_session,
    init_database_schema,
    settings,
)

__all__ = [
    "AsyncSessionLocal",
    "Base",
    "engine",
    "get_db",
    "get_db_session",
    "close_database",
    "init_database_schema",
]
