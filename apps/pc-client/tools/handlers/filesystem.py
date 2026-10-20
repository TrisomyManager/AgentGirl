"""Bounded UTF-8 reads and create-only writes in an explicit host workspace."""

import codecs
import os
import tempfile
from pathlib import Path

from policy import MAX_FILE_BYTES, get_policy, reparse
from registry import ToolResult, get_registry


def register_filesystem_handlers():
    reg = get_registry()

    @reg.register(
        "list_files", "列出专用工作区内的文件", risk="medium", requires_confirm=True
    )
    def list_files(params):
        policy = get_policy()
        path = policy.file_path(params.get("path", "."))
        entries = []
        with os.scandir(path) as iterator:
            for item in iterator:
                if reparse(Path(item.path)):
                    continue
                info = item.stat(follow_symlinks=False)
                if info.st_nlink > 1 and item.is_file(follow_symlinks=False):
                    continue
                entries.append(
                    {
                        "name": item.name,
                        "is_dir": item.is_dir(follow_symlinks=False),
                        "size": info.st_size,
                    }
                )
                if len(entries) == 101:
                    break
        return ToolResult(
            message="工作区文件列表",
            data={
                "path": str(path.relative_to(policy.root)),
                "entries": sorted(entries[:100], key=lambda item: item["name"]),
                "truncated": len(entries) > 100,
            },
        )

    @reg.register(
        "read_file", "读取工作区文本（最多 50 KB）", risk="high", requires_confirm=True
    )
    def read_file(params):
        policy = get_policy()
        path = policy.file_path(params.get("path", ""))
        with path.open("rb") as source:
            raw = source.read(MAX_FILE_BYTES + 1)
        truncated = len(raw) > MAX_FILE_BYTES
        try:
            decoder = codecs.getincrementaldecoder("utf-8")()
            content = decoder.decode(raw[:MAX_FILE_BYTES], final=not truncated)
        except UnicodeDecodeError:
            return ToolResult(ok=False, message="该文件不是 UTF-8 文本。")
        return ToolResult(
            message="已读取工作区文本",
            data={
                "path": str(path.relative_to(policy.root)),
                "content": content,
                "truncated": truncated,
            },
        )

    @reg.register(
        "write_file",
        "在工作区新建文本，不覆盖已有文件",
        risk="high",
        requires_confirm=True,
    )
    def write_file(params):
        policy = get_policy()
        path = policy.file_path(params.get("path", ""), create=True)
        raw = params.get("content", "").encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(
            prefix=".companion-", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
            # Atomic create: an existing target is never replaced.
            os.link(temporary, path)
        finally:
            os.unlink(temporary)
        return ToolResult(
            message="已在工作区新建文本",
            data={"path": str(path.relative_to(policy.root)), "bytes": len(raw)},
        )


register_filesystem_handlers()
