"""File system operations."""

import os
from pathlib import Path
from typing import Any, Dict

from registry import ToolResult, get_registry

MAX_READ_BYTES = 50_000
ALLOWED_READ_DIRS = [str(Path.home()), str(Path.home() / "Desktop"), str(Path.home() / "Documents")]


def register_filesystem_handlers() -> None:
    reg = get_registry()

    @reg.register("list_files", "List files in a directory", risk="medium")
    def list_files(params: Dict[str, Any]) -> ToolResult:
        path = params.get("path") or str(Path.home())
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return ToolResult(ok=False, message=f"Path not found: {path}")
        if not p.is_dir():
            return ToolResult(ok=False, message=f"Not a directory: {path}")

        entries = []
        try:
            for item in sorted(p.iterdir()):
                try:
                    stat = item.stat()
                    entries.append({
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })
                except OSError:
                    entries.append({"name": item.name, "is_dir": False, "size": 0, "modified": 0})
        except PermissionError:
            return ToolResult(ok=False, message=f"Permission denied: {path}")

        return ToolResult(
            ok=True,
            message=f"Listed {len(entries)} entries in {str(p)}",
            data={"path": str(p), "entries": entries[:100]},
        )

    @reg.register("read_file", "Read a text file (max 50KB)", risk="high", requires_confirm=True)
    def read_file(params: Dict[str, Any]) -> ToolResult:
        path = params.get("path", "").strip()
        if not path:
            return ToolResult(ok=False, message="No file path provided")
        p = Path(path).expanduser().resolve()

        allowed = any(str(p).startswith(str(Path(d).expanduser().resolve())) for d in ALLOWED_READ_DIRS)
        if not allowed:
            return ToolResult(ok=False, message="Access denied: outside allowed directories")

        try:
            content = p.read_text(encoding="utf-8")[:MAX_READ_BYTES]
            return ToolResult(
                ok=True,
                message=f"Read {len(content)} chars from {p.name}",
                data={"path": str(p), "content": content, "truncated": len(content) >= MAX_READ_BYTES},
            )
        except UnicodeDecodeError:
            return ToolResult(ok=False, message="Cannot read: file is not UTF-8 text")
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc))

    @reg.register("write_file", "Write text to a file", risk="high", requires_confirm=True)
    def write_file(params: Dict[str, Any]) -> ToolResult:
        path = params.get("path", "").strip()
        content = params.get("content", "")
        if not path:
            return ToolResult(ok=False, message="No file path provided")
        p = Path(path).expanduser().resolve()

        allowed = any(str(p).startswith(str(Path(d).expanduser().resolve())) for d in ALLOWED_READ_DIRS)
        if not allowed:
            return ToolResult(ok=False, message="Access denied: outside allowed directories")

        try:
            p.write_text(content, encoding="utf-8")
            return ToolResult(ok=True, message=f"Wrote {len(content)} chars to {p.name}")
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc))


register_filesystem_handlers()
