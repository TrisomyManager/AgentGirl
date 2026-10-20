import asyncio
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator

from action_executor.mcp_client import MCPHub, MCPServerConfig
from action_executor.registry import ActionRegistry, ActionResult, get_registry
from action_executor.tool_schema import canonical_schema

BACKEND = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("mcp_fixture_server.py")


def test_all_builtin_tools_export_valid_real_json_schemas_without_host_identity():
    tools = get_registry().mcp_tools()
    assert len(tools) == 13
    for tool in tools:
        schema = tool["inputSchema"]
        Draft202012Validator.check_schema(schema)
        assert schema["type"] == "object"
        assert not {"user_id", "session_id", "turn_id", "operation_id"} & schema.get("properties", {}).keys()
    assert next(tool for tool in tools if tool["name"] == "set_reminder")["annotations"]["destructiveHint"] is False


def test_invalid_server_configuration_never_leaves_partially_enabled_connections():
    hub = MCPHub()
    config = MCPServerConfig(name="duplicate", allowed_users=["owner"], command=sys.executable)
    with pytest.raises(ValueError, match="Duplicate"):
        hub.configure([config, config])
    assert not hub.connections


@pytest.mark.parametrize(
    "arguments",
    [
        {"user_id": "victim"},
        {"session_id": "victim"},
        {"value": float("nan")},
        {"value": True},
        {"value": -1},
        {"other": 5},
        [],
        None,
    ],
)
async def test_tool_arguments_are_validated_before_handler(arguments):
    registry = ActionRegistry()
    calls = []

    @registry.register(
        "local",
        "Test",
        {"type": "object", "properties": {"value": {"type": "integer", "minimum": 0}}, "required": ["value"]},
        requires_user_id=True,
    )
    async def handler(params):
        calls.append(params)
        return ActionResult()

    result = await registry.dispatch_contextual("local", arguments, user_id="owner")
    assert not result.ok and result.data["error"] == "invalid_arguments"
    assert not calls


async def test_context_is_bound_from_host_and_decorator_supports_real_schema():
    registry = ActionRegistry()
    seen = []

    @registry.register(
        "local",
        "Test",
        {"type": "object", "properties": {"user_id": {"type": "string"}}, "allOf": [{"required": ["user_id"]}]},
        requires_user_id=True,
    )
    async def handler(params):
        seen.append(params)
        return ActionResult(message="ok")

    assert (await registry.dispatch_contextual("local", {}, user_id="owner", session_id="mine", turn_id="turn")).ok
    assert seen[0]["user_id"] == "owner" and seen[0]["session_id"] == "mine"
    assert (await registry.dispatch_contextual("local", {}, user_id="")).data["error"] == "missing_user_id"
    assert canonical_schema("custom", {"count": "int required"})["required"] == ["count"]


@pytest.mark.parametrize("transport", ["stdio", "streamable_http"])
async def test_real_official_mcp_transport_discovery_calls_and_owner_isolation(transport):
    process = None
    hub = MCPHub()
    config = {"name": "synthetic", "allowed_users": ["owner"], "timeout_seconds": 10}
    try:
        if transport == "stdio":
            config.update(command=sys.executable, args=[str(FIXTURE)])
        else:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            process = subprocess.Popen(
                [sys.executable, str(FIXTURE), "streamable-http", str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            async with httpx.AsyncClient() as client:
                for _ in range(100):
                    try:
                        await client.get(f"http://127.0.0.1:{port}/mcp")
                        break
                    except httpx.ConnectError:
                        await asyncio.sleep(0.05)
                else:
                    pytest.fail("Synthetic MCP HTTP server did not start")
            config.update(transport=transport, url=f"http://127.0.0.1:{port}/mcp")
        hub.configure([MCPServerConfig(**config)])
        assert await hub.tools_for("another-user") == []
        tools = await hub.tools_for("owner")
        assert {tool["name"] for tool in tools} == {"synthetic__add", "synthetic__who"}
        identity_tool = next(tool for tool in tools if tool["name"] == "synthetic__who")
        assert "user_id" not in identity_tool["inputSchema"]["properties"]
        assert (await hub.call("synthetic__who", {}, user_id="owner")).data["mcp_result"]["structuredContent"][
            "result"
        ] == "owner"
        assert not (await hub.call("synthetic__who", {"user_id": "victim"}, user_id="owner")).ok
        # Calls occur from tasks different from the worker owning transport scopes.
        results = await asyncio.gather(
            *(hub.call("synthetic__add", {"a": a, "b": 3}, user_id="owner") for a in range(3))
        )
        assert all(result.ok for result in results)
        assert results[2].data["mcp_result"]["structuredContent"]["result"] == 5
        assert not (await hub.call("synthetic__change", {"value": "no"}, user_id="owner")).ok
        assert not (await hub.call("synthetic__add", {"a": "bad", "b": 1}, user_id="owner")).ok
        assert not (await hub.call("synthetic__add", {"a": 1, "b": 2}, user_id="another-user")).ok
    finally:
        await hub.close()
        if process:
            process.terminate()
            await asyncio.to_thread(process.wait, timeout=10)


async def test_builtin_mcp_stdio_bridge_keeps_stdout_valid_and_binds_identity(tmp_path):
    hub = MCPHub()
    hub.configure(
        [
            MCPServerConfig(
                name="local",
                allowed_users=["host-user"],
                command=sys.executable,
                args=[str(BACKEND / "mcp_actions_server.py"), "--user-id", "host-user"],
                env={
                    "COMPANION_LITE_MODE": "true",
                    "COMPANION_LITE_DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path.as_posix()}/mcp.db",
                },
                allow_mutations=True,
            )
        ]
    )
    try:
        tools = await hub.tools_for("host-user")
        assert len(tools) == 13
        result = await hub.call("local__get_time", {}, user_id="host-user")
        assert result.ok and "现在是" in result.message
        assert not (await hub.call("local__list_reminders", {"user_id": "other"}, user_id="host-user")).ok
        created = await hub.call(
            "local__set_reminder",
            {"text": "synthetic-test", "delay_seconds": 600, "repeat_interval_seconds": 120},
            user_id="host-user",
        )
        assert created.ok
        reminders = await hub.call("local__list_reminders", {}, user_id="host-user")
        data = reminders.data["mcp_result"]["structuredContent"]["data"]["reminders"]
        assert len(data) == 1 and data[0]["user_id"] == "host-user" and data[0]["repeat_interval_seconds"] == 120
    finally:
        await hub.close()
