"""Bounded bundled catalog. Installation never edits host execution grants."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from importlib.resources import files
from pathlib import Path
from stat import FILE_ATTRIBUTE_REPARSE_POINT, S_ISLNK

from action_executor.plugins import PluginGrant, PluginManager, PluginManifest

_CATALOG = {
    "text_tools": {
        "description": "统计字数、行数、拉丁单词和汉字数量，适合检查文章篇幅。",
        "permissions": "纯本地文本计算；不访问文件、网络或模型。",
        "source": "应用内置",
    },
}


class CatalogError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message
        super().__init__(message)


def _package(identifier: str):
    if identifier not in _CATALOG:
        raise CatalogError(404, "目录中没有这项扩展。")
    source = files("action_executor").joinpath("catalog", identifier)
    manifest, code = source.joinpath("plugin.json").read_bytes(), source.joinpath("plugin.py").read_bytes()
    info = PluginManifest.model_validate_json(manifest)
    if info.id != identifier or len(manifest) > 16384 or len(code) > 1024 * 1024:
        raise CatalogError(503, "扩展包不可用。")
    digest = hashlib.sha256(manifest + code).hexdigest()
    return info, manifest, code, digest


def catalog_status(manager: PluginManager, *, enabled: bool):
    installed = {item["id"]: item for item in manager.status()}
    entries = []
    for identifier, details in _CATALOG.items():
        info, _, _, digest = _package(identifier)
        local = installed.get(identifier)
        exists = manager.directory is not None and os.path.lexists(manager.directory / identifier)
        entries.append(
            {
                **details,
                "id": identifier,
                "name": info.name,
                "version": info.version,
                "sha256": digest,
                "installed": bool(local) or exists,
                "runtime_status": local["status"] if local else ("needs_inspection" if exists else "not_installed"),
            }
        )
    return {"installation_enabled": enabled and manager.directory is not None, "entries": entries}


def _safe_root(root: Path):
    root = root.absolute()
    # Installation is an explicitly granted host operation. Reject linked roots
    # and ancestors; it must never write through a pre-existing junction.
    for part in (*reversed(root.parents), root):
        stat = part.lstat()
        if S_ISLNK(stat.st_mode) or getattr(stat, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
            raise CatalogError(409, "扩展目录不能经过链接或重解析点。")
    if not root.is_dir():
        raise CatalogError(409, "宿主扩展目录不可用。")
    return root


def _install(root: Path, config_file: Path | None, identifier: str, expected_sha256: str):
    info, manifest, code, digest = _package(identifier)
    if digest != expected_sha256:
        raise CatalogError(409, "扩展版本已变化，请刷新目录后重试。")
    if config_file is not None:
        try:
            if config_file.stat().st_size > 65536:
                raise ValueError("Invalid config")
            config = json.loads(config_file.read_text(encoding="utf-8"))
            grants = [PluginGrant.model_validate(item) for item in config["plugins"]]
            if any(grant.id == identifier and grant.enabled for grant in grants):
                raise CatalogError(409, "请宿主先停用该名称的预先授权，安装后再审阅启用。")
        except CatalogError:
            raise
        except Exception:
            raise CatalogError(409, "请宿主先修复扩展授权配置。") from None
    root = _safe_root(root)
    target = root / identifier
    try:
        # mkdir is the no-clobber claim on both Windows and POSIX. The scanner
        # executes nothing until the final manifest and a separate host grant.
        target.mkdir()
    except FileExistsError:
        raise CatalogError(409, "该名称已存在；不会覆盖现有扩展。") from None
    try:
        for name, content in (("plugin.py", code), ("plugin.json", manifest)):
            with (target / name).open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        # Keep an incomplete directory visible as invalid rather than recursively
        # deleting paths after an unknown partial write. Never activate it.
        raise CatalogError(503, "安装未完成；请由宿主检查扩展目录。") from None
    return {
        "id": info.id,
        "version": info.version,
        "sha256": digest,
        "status": "installed",
        "activation": "host_grant_required",
    }


async def install_catalog_plugin(manager: PluginManager, identifier: str, expected_sha256: str, *, enabled: bool):
    if not enabled or manager.directory is None:
        raise CatalogError(403, "宿主尚未开放内置扩展安装。")
    async with manager._installation_lock:
        worker = asyncio.create_task(
            asyncio.to_thread(_install, manager.directory, manager.config_file, identifier, expected_sha256)
        )
        try:
            result = await asyncio.shield(worker)
        except asyncio.CancelledError:
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not worker.cancelled():
                worker.exception()
            raise
        except OSError:
            raise CatalogError(503, "扩展目录不可写或不可用，请联系宿主。") from None
        await manager.refresh()
        return result
