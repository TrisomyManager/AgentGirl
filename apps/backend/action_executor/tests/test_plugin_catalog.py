import asyncio
import json
import threading

import pytest

from action_executor.plugin_catalog import CatalogError, catalog_status, install_catalog_plugin
from action_executor.plugins import PluginCallContext, PluginManager


async def test_bundled_install_is_disabled_then_host_can_authorize_actual_tool(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"plugins": []}', encoding="utf-8")
    root = tmp_path / "plugins"
    root.mkdir()
    manager = PluginManager(root, config)
    entry = catalog_status(manager, enabled=False)["entries"][0]
    with pytest.raises(CatalogError) as denied:
        await install_catalog_plugin(manager, entry["id"], entry["sha256"], enabled=False)
    assert denied.value.status == 403
    assert not list(root.iterdir())
    try:
        result = await install_catalog_plugin(manager, entry["id"], entry["sha256"], enabled=True)
        assert result["activation"] == "host_grant_required"
        assert manager.status()[0]["status"] == "disabled"
        assert not manager.tools_for("alice")
        config.write_text(json.dumps({"plugins": [{"id": "text_tools", "enabled": True, "allowed_users": ["alice"]}]}))
        await manager.refresh()
        result = await manager.call(
            "plugin_text_tools__statistics", {"text": "你好 world\nhello again"}, PluginCallContext("alice")
        )
        assert result.ok and result.data == {
            "characters": 20,
            "non_whitespace": 17,
            "lines": 2,
            "latin_words": 3,
            "han_characters": 2,
        }
        assert not manager.tools_for("bob")
        assert catalog_status(manager, enabled=True)["entries"][0]["runtime_status"] == "loaded"
    finally:
        await manager.close()


async def test_install_rejects_unknown_changed_existing_and_pregranted_packages(tmp_path):
    manager = PluginManager(tmp_path)
    entry = catalog_status(manager, enabled=True)["entries"][0]
    for identifier, digest, expected in [("../../elsewhere", entry["sha256"], 404), (entry["id"], "0" * 64, 409)]:
        with pytest.raises(CatalogError) as error:
            await install_catalog_plugin(manager, identifier, digest, enabled=True)
        assert error.value.status == expected
    config = tmp_path / "grants.json"
    config.write_text(json.dumps({"plugins": [{"id": "text_tools", "enabled": True, "allowed_users": ["alice"]}]}))
    manager.config_file = config
    with pytest.raises(CatalogError, match="预先授权"):
        await install_catalog_plugin(manager, entry["id"], entry["sha256"], enabled=True)
    assert not (tmp_path / entry["id"]).exists()
    manager.config_file = None
    existing = tmp_path / entry["id"]
    existing.mkdir()
    (existing / "plugin.py").write_text("original")
    with pytest.raises(CatalogError, match="不会覆盖"):
        await install_catalog_plugin(manager, entry["id"], entry["sha256"], enabled=True)
    assert (existing / "plugin.py").read_text() == "original"


async def test_install_rejects_linked_roots(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(root, target_is_directory=True)
    except OSError:
        if __import__("os").name != "nt":
            pytest.skip("Symlink creation unavailable")
        import subprocess

        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(root)], capture_output=True, check=True)
    manager = PluginManager(link)
    entry = catalog_status(manager, enabled=True)["entries"][0]
    with pytest.raises(CatalogError, match="重解析"):
        await install_catalog_plugin(manager, entry["id"], entry["sha256"], enabled=True)
    assert not list(root.iterdir())


async def test_cancelled_install_drains_disk_worker_and_retry_never_overwrites(tmp_path, monkeypatch):
    from action_executor import plugin_catalog

    manager = PluginManager(tmp_path)
    entry = catalog_status(manager, enabled=True)["entries"][0]
    original = plugin_catalog._install
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def delayed(*args):
        started.set()
        assert release.wait(5)
        try:
            return original(*args)
        finally:
            finished.set()

    monkeypatch.setattr(plugin_catalog, "_install", delayed)
    task = asyncio.create_task(install_catalog_plugin(manager, entry["id"], entry["sha256"], enabled=True))
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()
    with pytest.raises(CatalogError, match="不会覆盖"):
        await install_catalog_plugin(manager, entry["id"], entry["sha256"], enabled=True)
