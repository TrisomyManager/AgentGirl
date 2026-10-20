import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from action_executor.plugins import PluginCallContext, PluginManager
from action_executor.registry import ActionRegistry
from action_executor.tool_catalog import ToolCatalog, ToolContext
from shared_runtime.access import Principal, current_principal
from shared_runtime.user_lifecycle import erase_user_work, user_operation

SOURCE = """
import asyncio
from action_executor.registry import ActionResult

async def setup(api):
    owner = asyncio.current_task()
    async def close():
        assert asyncio.current_task() is owner, "cleanup changed worker task"
        with open(__file__ + ".closed", "a") as file:
            file.write("closed\\n")
    api.resources.push_async_callback(close)
    async def echo(arguments, context):
        if arguments.get("wait"):
            await asyncio.sleep(arguments["wait"])
        return ActionResult(message="VERSION:" + arguments["text"],
                            data={"user": context.user_id, "op": context.operation_id})
    api.add_tool("echo", "test echo", {"type":"object", "properties": {
        "text":{"type":"string", "maxLength":100}, "wait":{"type":"number", "minimum":0, "maximum":1}},
        "required":["text"], "additionalProperties":False}, echo)
    api.add_tool("write", "test write", {"type":"object", "properties":{},
                 "additionalProperties":False}, echo, read_only=False)
"""


def install(tmp_path, version="one", *, enabled=True, users=None):
    root = tmp_path / "plugins"
    folder = root / "echo"
    folder.mkdir(parents=True, exist_ok=True)
    entry = folder / "plugin.py"
    entry.write_text(SOURCE.replace("VERSION", version), encoding="utf-8")
    (folder / "plugin.json").write_text(
        json.dumps({"id": "echo", "name": "Echo", "version": version}), encoding="utf-8"
    )
    config = tmp_path / "grants.json"
    config.write_text(
        json.dumps({"plugins": [{"id": "echo", "enabled": enabled, "allowed_users": users or ["alice"]}]}),
        encoding="utf-8",
    )
    return PluginManager(root, config, poll_seconds=0.1), entry, config


async def test_real_plugin_load_schema_identity_scopes_and_worker_owned_cleanup(tmp_path):
    manager, entry, _ = install(tmp_path)
    await manager.start()
    try:
        assert [tool["name"] for tool in manager.tools_for("alice")] == ["plugin_echo__echo"]
        assert not manager.tools_for("bob")
        bad = await manager.call("plugin_echo__echo", {"text": "x", "user_id": "bob"}, PluginCallContext("alice"))
        assert not bad.ok and bad.data["error"] == "invalid_arguments"
        forbidden = await manager.call("plugin_echo__write", {}, PluginCallContext("alice"))
        assert not forbidden.ok
        catalog = ToolCatalog(ActionRegistry(), AsyncMock(tools_for=AsyncMock(return_value=[])), manager)
        tools = await catalog.tools_for(ToolContext("alice"))
        assert tools[0]["inputSchema"]["required"] == ["text"]
        result = await catalog.call(
            "plugin_echo__echo", {"text": "hello"}, ToolContext("alice"), operation_id="receipt"
        )
        assert result.ok and result.message == "one:hello" and result.data == {"user": "alice", "op": "receipt"}
    finally:
        await manager.close()
    assert Path(str(entry) + ".closed").read_text().splitlines() == ["closed"]
    assert not any(name.startswith("_companion_plugin_echo_") for name in sys.modules)


async def test_plugin_work_copies_each_call_identity_and_erasure_does_not_poison_the_shared_worker(tmp_path):
    manager, entry, _ = install(tmp_path, users=["plugin_alice", "plugin_bob"])
    source = SOURCE.replace(
        "from action_executor.registry import ActionResult",
        "from action_executor.registry import ActionResult\nfrom shared_runtime.access import current_principal",
    )
    source = source.replace(
        'if arguments.get("wait"):',
        'with open(__file__ + ".entered", "w") as marker: marker.write("started")\n        if arguments.get("wait"):',
    )
    source = source.replace('"user": context.user_id', '"user": current_principal.get().user_id')
    entry.write_text(source)
    async with user_operation("plugin_alice"):
        await manager.start()
    token = current_principal.set(Principal("plugin_alice", "user"))
    pending = asyncio.create_task(
        manager.call("plugin_echo__echo", {"text": "old", "wait": 1}, PluginCallContext("plugin_alice"))
    )
    current_principal.reset(token)
    try:
        async with asyncio.timeout(2):
            while not Path(str(entry) + ".entered").exists():
                await asyncio.sleep(0.01)
        async with erase_user_work("plugin_alice"):
            pass
        assert not (await pending).ok
        token = current_principal.set(Principal("plugin_bob", "user"))
        try:
            result = await manager.call("plugin_echo__echo", {"text": "new"}, PluginCallContext("plugin_bob"))
            assert result.ok and result.data["user"] == "plugin_bob"
        finally:
            current_principal.reset(token)
    finally:
        await manager.close()


async def test_hot_reload_does_not_use_stale_pyc_and_old_calls_finish_once(tmp_path):
    manager, entry, config = install(tmp_path)
    await manager.start()
    try:
        old = asyncio.create_task(
            manager.call("plugin_echo__echo", {"text": "old", "wait": 0.15}, PluginCallContext("alice"))
        )
        await asyncio.sleep(0.03)
        # Same-second, same-sized source edits must still change the implementation.
        entry.write_text(SOURCE.replace("VERSION", "two"), encoding="utf-8")
        async with asyncio.timeout(3):
            while True:
                result = await manager.call("plugin_echo__echo", {"text": "new"}, PluginCallContext("alice"))
                if result.message == "two:new":
                    break
                await asyncio.sleep(0.05)
        assert (await old).message == "one:old"
        config.write_text('{"plugins":[]}', encoding="utf-8")
        await manager.refresh()
        assert not manager.tools_for("alice")
        assert not (await manager.call("plugin_echo__echo", {"text": "late"}, PluginCallContext("alice"))).ok
    finally:
        await manager.close()
    assert len(Path(str(entry) + ".closed").read_text().splitlines()) == 2


async def test_failed_reload_preserves_valid_generation_but_revised_grants_revoke_it(tmp_path):
    manager, entry, config = install(tmp_path)
    await manager.refresh()
    try:
        entry.write_text("syntax error!", encoding="utf-8")
        await manager.refresh()
        assert manager.status()[0]["status"] == "load_failed"
        assert (await manager.call("plugin_echo__echo", {"text": "still works"}, PluginCallContext("alice"))).ok
        config.write_text(
            json.dumps({"plugins": [{"id": "echo", "enabled": True, "allowed_users": ["bob"]}]}), encoding="utf-8"
        )
        await manager.refresh()
        assert not manager.tools_for("alice") and not manager.tools_for("bob")
    finally:
        await manager.close()


@pytest.mark.parametrize(
    "config",
    ['{"plugins":[{"id":"../escape","enabled":true}]}', '{"plugins":[{"id":"echo","allowed_users":["*"]}]}', "broken"],
)
async def test_invalid_host_policy_fails_closed_without_exposing_contents(tmp_path, config):
    manager, _, path = install(tmp_path)
    await manager.refresh()
    path.write_text(config, encoding="utf-8")
    await manager.refresh()
    assert not manager.tools_for("alice")
    assert "invalid_config" in str(manager.status())
    assert config not in str(manager.status())
    await manager.close()


async def test_cancellation_and_shutdown_drain_calls_and_release_workers(tmp_path):
    manager, _, _ = install(tmp_path)
    await manager.start()
    call = asyncio.create_task(
        manager.call("plugin_echo__echo", {"text": "cancel", "wait": 1}, PluginCallContext("alice"))
    )
    await asyncio.sleep(0.02)
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    await manager.close()
    assert not [
        task
        for task in asyncio.all_tasks()
        if task.get_name().startswith(("plugin:", "plugin-tool:", "plugin-watcher"))
    ]


async def test_setup_failure_closes_resources_in_its_owner_task(tmp_path):
    manager, entry, _ = install(tmp_path)
    entry.write_text(
        SOURCE.replace(
            '    api.add_tool("echo",', '    raise RuntimeError("private setup detail")\n    api.add_tool("echo",'
        ),
        encoding="utf-8",
    )
    await manager.refresh()
    assert manager.status()[0]["status"] == "load_failed"
    assert "private" not in str(manager.status())
    assert Path(str(entry) + ".closed").read_text().strip() == "closed"
    await manager.refresh()
    assert Path(str(entry) + ".closed").read_text().splitlines() == ["closed"]
    await manager.close()


async def test_directory_discovery_does_not_execute_a_disabled_plugin(tmp_path):
    _, entry, _ = install(tmp_path)
    entry.write_text('raise RuntimeError("must not execute")', encoding="utf-8")
    manager = PluginManager(tmp_path / "plugins")
    await manager.start()
    assert manager.status()[0]["status"] == "disabled"
    assert not manager.tools_for("alice")
    await manager.close()


async def test_mutation_timeout_is_unknown_and_is_never_replayed(tmp_path):
    manager, entry, config = install(tmp_path)
    entry.write_text(
        """
import asyncio
from action_executor.registry import ActionResult
async def setup(api):
    async def write(arguments, context):
        with open(__file__ + ".attempts", "a") as file:
            file.write("once\\n")
        await asyncio.sleep(1)
        return ActionResult(message="done")
    api.add_tool("write", "write", {"type":"object", "properties":{}}, write, read_only=False)
""",
        encoding="utf-8",
    )
    config.write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "id": "echo",
                        "enabled": True,
                        "allowed_users": ["alice"],
                        "allow_mutations": True,
                        "timeout_seconds": 0.1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    await manager.start()
    try:
        result = await manager.call("plugin_echo__write", {}, PluginCallContext("alice"))
        assert not result.ok and result.data["error"] == "outcome_unknown"
        await asyncio.sleep(0.15)
        assert Path(str(entry) + ".attempts").read_text().splitlines() == ["once"]
    finally:
        await manager.close()
