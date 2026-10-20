"""Host-owned capability/file boundaries, not an OS sandbox for malicious local programs."""

import ipaddress
import json
import os
import stat
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_CAPABILITIES = frozenset(
    {"system_info", "get_device_status", "show_notification", "open_url"}
)
OPTIONAL_CAPABILITIES = frozenset(
    {
        "list_files",
        "read_file",
        "write_file",
        "clipboard_read",
        "clipboard_write",
        "list_processes",
        "screenshot",
    }
)
CONFIRMATION_REQUIRED = OPTIONAL_CAPABILITIES | {"open_url"}
FILE_CAPABILITIES = frozenset({"list_files", "read_file", "write_file", "screenshot"})
MAX_PAYLOAD_BYTES = 65536
MAX_FILE_BYTES = 50000


def public_url(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2048
        or any(c.isspace() or ord(c) < 32 for c in value)
    ):
        return False
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        if (
            url.scheme not in {"http", "https"}
            or not host
            or url.username
            or url.password
            or "\\" in value
        ):
            return False
        if url.port is not None and not 1 <= url.port <= 65535:
            return False
        if (
            "." not in host
            or host.endswith((".localhost", ".local", ".internal"))
            or host == "localhost"
        ):
            return False
        if host.replace(".", "").isdigit() or host.startswith("0x"):
            return ipaddress.ip_address(host).is_global
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return not any(not part for part in host.split("."))
    except ValueError:
        return False


def reparse(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400
    )


class ExecutionPolicy:
    def __init__(self, capabilities=None, root=None):
        self.capabilities = set(
            DEFAULT_CAPABILITIES if capabilities is None else capabilities
        )
        self.capabilities &= DEFAULT_CAPABILITIES | OPTIONAL_CAPABILITIES
        self.root = None
        self.root_identity = None
        if root:
            candidate = Path(root)
            if not candidate.is_absolute() or not candidate.is_dir():
                raise ValueError("A dedicated absolute workspace directory is required")
            if any(reparse(path) for path in [candidate, *candidate.parents]):
                raise ValueError(
                    "Workspace cannot traverse symbolic links or reparse points"
                )
            resolved = candidate.resolve(strict=True)
            if resolved in {Path(resolved.anchor), Path.home().resolve()}:
                raise ValueError("Use a dedicated workspace directory")
            self.root = resolved
            info = resolved.stat()
            self.root_identity = (info.st_dev, info.st_ino)
        if self.root is None:
            self.capabilities -= FILE_CAPABILITIES

    @classmethod
    def from_env(cls):
        extra = {
            name.strip()
            for name in os.environ.get("XIAONUAN_TOOL_CAPABILITIES", "").split(",")
            if name.strip()
        }
        return cls(
            DEFAULT_CAPABILITIES | (extra & OPTIONAL_CAPABILITIES),
            os.environ.get("XIAONUAN_SANDBOX_ROOT"),
        )

    def authorize(self, name, params, *, approved=False):
        if name not in self.capabilities:
            raise PermissionError("该能力未由本机宿主启用。")
        if (
            not isinstance(params, dict)
            or len(json.dumps(params, ensure_ascii=False, allow_nan=False).encode())
            > MAX_PAYLOAD_BYTES
        ):
            raise ValueError("工具参数格式或大小不正确。")
        fields = {
            "open_url": {"url"},
            "show_notification": {"title", "body", "text"},
            "list_files": {"path"},
            "read_file": {"path"},
            "write_file": {"path", "content"},
            "clipboard_write": {"text"},
        }.get(name, set())
        if set(params) - fields or any(
            not isinstance(value, str) for value in params.values()
        ):
            raise ValueError("工具参数格式不正确。")
        if name in CONFIRMATION_REQUIRED and approved is not True:
            raise PermissionError("此操作需要本机确认。")
        if name == "open_url" and not public_url(params.get("url")):
            raise ValueError("只允许无凭据的公开 HTTP/HTTPS 地址。")
        if name == "show_notification" and (
            len(params.get("title", "")) > 100
            or len(params.get("body", params.get("text", ""))) > 2000
        ):
            raise ValueError("通知内容过长。")
        if name in {"write_file", "clipboard_write"}:
            text = params.get("content" if name == "write_file" else "text", "")
            if len(text.encode()) > MAX_FILE_BYTES:
                raise ValueError("文本超过 50 KB。")
        if name in {"list_files", "read_file", "write_file"}:
            self.file_path(
                params.get("path", "." if name == "list_files" else ""),
                create=name == "write_file",
            )

    def file_path(self, value, *, create=False):
        if (
            self.root is None
            or not isinstance(value, str)
            or not value
            or len(value) > 1024
            or "\x00" in value
        ):
            raise PermissionError("未配置专用文件工作区或路径无效。")
        path = Path(value)
        if (
            ".." in path.parts
            or any(":" in part for part in path.parts[1:] if path.is_absolute())
            or (not path.is_absolute() and ":" in value)
        ):
            raise PermissionError("不允许路径穿越或替代数据流。")
        candidate = path if path.is_absolute() else self.root / path
        try:
            relative = candidate.relative_to(self.root)
        except ValueError:
            raise PermissionError("文件不在专用工作区内。") from None
        current = self.root
        info = current.stat()
        if (
            any(reparse(item) for item in [current, *current.parents])
            or (info.st_dev, info.st_ino) != self.root_identity
        ):
            raise PermissionError("工作区发生变化。")
        for part in relative.parts:
            if part.rstrip(" .") != part or unicodedata.normalize(
                "NFKC", part.split(".")[0]
            ).upper() in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *[f"COM{i}" for i in range(1, 10)],
                *[f"LPT{i}" for i in range(1, 10)],
            }:
                raise PermissionError("不允许特殊设备路径。")
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                if not create or current != candidate:
                    raise PermissionError("路径不存在。") from None
                break
            if reparse(current) or (stat.S_ISREG(info.st_mode) and info.st_nlink > 1):
                raise PermissionError("不允许链接、重解析点或硬链接。")
            if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):
                raise PermissionError("不允许特殊文件。")
        resolved = candidate.resolve(strict=not create)
        if not resolved.is_relative_to(self.root):
            raise PermissionError("文件不在专用工作区内。")
        if create and (
            resolved.exists()
            or resolved.suffix.lower() not in {".txt", ".md", ".json", ".csv", ".tsv"}
        ):
            raise PermissionError(
                "只允许新建文本文件，不覆盖现有文件或写入可执行文件。"
            )
        return resolved


_policy = None


def get_policy():
    global _policy
    if _policy is None:
        _policy = ExecutionPolicy.from_env()
    return _policy
