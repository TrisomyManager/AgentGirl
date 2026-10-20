"""Host-configured MCP connections, scoped by user and owned by one worker task.

Transport/session context managers must be entered and closed in the same task
because the official SDK owns AnyIO cancellation scopes. Chat never supplies
commands, headers, environment variables, or connection URLs.
"""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Literal

import httpx
from jsonschema import Draft202012Validator, ValidationError
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, ConfigDict, Field, model_validator

from action_executor.registry import ActionResult
from action_executor.tool_schema import canonical_schema


class MCPServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,31}$")
    transport: Literal["stdio", "streamable_http"] = "stdio"
    allowed_users: list[str] = Field(min_length=1)
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict, repr=False)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict, repr=False)
    timeout_seconds: float = Field(default=15, ge=0.1, le=120)
    # Unannotated/unsafe tools are excluded unless the host explicitly opts in.
    allow_mutations: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def validate_transport(self):
        if any(not user.strip() or user == "*" for user in self.allowed_users):
            raise ValueError("Specify explicit users for each MCP server")
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio requires a host-configured command")
        if self.transport == "streamable_http" and not re.match(r"^https?://", self.url or ""):
            raise ValueError("streamable_http requires an http(s) URL")
        return self


@dataclass
class _Job:
    name: str
    arguments: dict
    future: asyncio.Future


class MCPConnection:
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.tools: dict[str, dict] = {}
        self._queue: asyncio.Queue[_Job | None] = asyncio.Queue(maxsize=32)
        self._worker: asyncio.Task | None = None
        self._ready: asyncio.Future | None = None
        self._closing = False

    async def start(self):
        if self._closing:
            raise RuntimeError("MCP connection is closing")
        if self._worker is None:
            self._ready = asyncio.get_running_loop().create_future()
            self._worker = asyncio.create_task(self._run(), name=f"mcp:{self.config.name}")
        await asyncio.wait_for(asyncio.shield(self._ready), self.config.timeout_seconds + 1)

    async def _run(self):
        failure = RuntimeError("MCP connection unavailable")
        current_job = None
        try:
            async with AsyncExitStack() as stack:
                if self.config.transport == "stdio":
                    params = StdioServerParameters(
                        command=self.config.command, args=self.config.args, env=self.config.env or None
                    )
                    read, write = await stack.enter_async_context(stdio_client(params))
                else:
                    client = await stack.enter_async_context(
                        httpx.AsyncClient(headers=self.config.headers, timeout=self.config.timeout_seconds)
                    )
                    read, write, _ = await stack.enter_async_context(
                        streamable_http_client(self.config.url, http_client=client)
                    )
                session = await stack.enter_async_context(
                    ClientSession(read, write, read_timeout_seconds=timedelta(seconds=self.config.timeout_seconds))
                )
                async with asyncio.timeout(self.config.timeout_seconds):
                    await session.initialize()
                    cursor = None
                    for _ in range(10):
                        page = await session.list_tools(cursor=cursor)
                        for tool in page.tools:
                            meta = tool.model_dump(by_alias=True, exclude_none=True)
                            Draft202012Validator.check_schema(meta["inputSchema"])
                            if tool.name in self.tools or len(self.tools) >= 256:
                                raise ValueError("Duplicate or excessive MCP tools")
                            if not self.config.allow_mutations and not meta.get("annotations", {}).get(
                                "readOnlyHint", False
                            ):
                                continue
                            self.tools[tool.name] = meta
                        cursor = page.nextCursor
                        if not cursor:
                            break
                    else:
                        raise ValueError("Excessive MCP pagination")
                self._ready.set_result(True)
                while True:
                    job = await self._queue.get()
                    if job is None:
                        break
                    if job.future.cancelled():
                        continue
                    current_job = job
                    try:
                        async with asyncio.timeout(self.config.timeout_seconds):
                            result = await session.call_tool(job.name, job.arguments)
                        payload = result.model_dump(by_alias=True, exclude_none=True)
                        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
                        if len(encoded) > 64000:
                            outcome = ActionResult(
                                ok=False,
                                message="工具返回的结果过大，请缩小查询范围。",
                                data={"error": "result_too_large"},
                            )
                        else:
                            message = "\n".join(item.text for item in result.content if item.type == "text")
                            outcome = ActionResult(
                                ok=not result.isError, message=message[:12000], data={"mcp_result": payload}
                            )
                    except Exception:
                        # A lost reply is not evidence that a remote mutation failed.
                        outcome = ActionResult(
                            ok=False,
                            message="外部工具未返回确定结果，已停止后续执行。",
                            data={"error": "outcome_unknown"},
                        )
                    if not job.future.done():
                        job.future.set_result(outcome)
                    current_job = None
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._ready and not self._ready.done():
                self._ready.set_exception(failure)
        finally:
            self._closing = True
            if current_job and not current_job.future.done():
                current_job.future.set_result(
                    ActionResult(
                        ok=False, message="连接已中断，请核对工具实际结果。", data={"error": "outcome_unknown"}
                    )
                )
            if self._ready and not self._ready.done():
                self._ready.set_exception(failure)
            while not self._queue.empty():
                job = self._queue.get_nowait()
                if job and not job.future.done():
                    job.future.set_result(
                        ActionResult(ok=False, message="工具连接已关闭。", data={"error": "connection_closed"})
                    )

    async def call(self, name: str, arguments: dict) -> ActionResult:
        await self.start()
        if name not in self.tools:
            return ActionResult(ok=False, message="工具不可用。", data={"error": "unknown_tool"})
        try:
            json.dumps(arguments, allow_nan=False)
            Draft202012Validator(self.tools[name]["inputSchema"]).validate(arguments)
        except (ValidationError, ValueError, TypeError):
            return ActionResult(ok=False, message="工具参数格式不正确。", data={"error": "invalid_arguments"})
        future = asyncio.get_running_loop().create_future()
        try:
            self._queue.put_nowait(_Job(name, arguments, future))
        except asyncio.QueueFull:
            return ActionResult(ok=False, message="工具正忙，请稍后再试。", data={"error": "tool_busy"})
        try:
            return await asyncio.wait_for(future, self.config.timeout_seconds * 2)
        except TimeoutError:
            return ActionResult(
                ok=False, message="工具结果暂时无法确认，请先检查实际状态。", data={"error": "outcome_unknown"}
            )

    async def close(self):
        self._closing = True
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None


@dataclass
class MCPHub:
    connections: dict[str, MCPConnection] = field(default_factory=dict)

    def configure(self, configs: list[MCPServerConfig]):
        if self.connections:
            raise RuntimeError("Close MCP connections before reconfiguration")
        configured = {}
        seen = set()
        for config in configs:
            if config.name in seen:
                raise ValueError("Duplicate MCP server name")
            seen.add(config.name)
            if config.enabled:
                configured[config.name] = MCPConnection(config)
        self.connections = configured

    async def tools_for(self, user_id: str) -> list[dict]:
        result = []
        for name, connection in self.connections.items():
            if user_id not in connection.config.allowed_users:
                continue
            try:
                await connection.start()
            except Exception:
                continue
            result.extend(
                {
                    **meta,
                    "name": f"{name}__{tool_name}",
                    "inputSchema": canonical_schema(tool_name, meta["inputSchema"]),
                }
                for tool_name, meta in connection.tools.items()
            )
        return result

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        user_id: str,
        session_id: str = "",
        turn_id: str = "",
        operation_id: str = "",
    ) -> ActionResult:
        server, _, tool = name.partition("__")
        connection = self.connections.get(server)
        if not connection or user_id not in connection.config.allowed_users:
            return ActionResult(ok=False, message="工具不可用。", data={"error": "unknown_tool"})
        await connection.start()
        if tool not in connection.tools:
            return ActionResult(ok=False, message="工具不可用。", data={"error": "unknown_tool"})
        identity = {"user_id": user_id, "session_id": session_id, "turn_id": turn_id, "operation_id": operation_id}
        try:
            if not isinstance(arguments, dict) or identity.keys() & arguments.keys():
                raise ValueError("Host identity cannot be supplied by tool consumers")
            Draft202012Validator(canonical_schema(tool, connection.tools[tool]["inputSchema"])).validate(arguments)
        except (ValidationError, TypeError, ValueError):
            return ActionResult(ok=False, message="工具参数格式不正确。", data={"error": "invalid_arguments"})
        properties = connection.tools[tool]["inputSchema"].get("properties", {})
        bound = {**arguments, **{key: value for key, value in identity.items() if key in properties}}
        return await connection.call(tool, bound)

    async def close(self):
        await asyncio.gather(*(item.close() for item in self.connections.values()))
        self.connections.clear()

    def load_file(self, path: str):
        """Only called by host startup; never return/log the secret-bearing input."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.configure([MCPServerConfig.model_validate(item) for item in payload["servers"]])


mcp_hub = MCPHub()
