"""Specialist delegation through injected host ports, shared by both chat paths."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from action_executor.task_agent import Progress
from action_executor.task_policy import is_multistep_request, task_tool_scope
from action_executor.tool_catalog import ToolContext
from core_orchestrator.routing_rules import can_execute_device_request, is_declined_operation
from shared_contracts.models import TurnContext

ToolPort = Callable[[TurnContext, str], Awaitable[dict | None]]
DevicePort = Callable[[TurnContext], Awaitable[dict | None]]


@dataclass
class ChatAgent:
    generate: Callable[..., Awaitable[str]]
    stream: Callable[..., AsyncIterator[str]]


@dataclass
class MemoryAgent:
    tool: ToolPort

    async def execute(self, context: TurnContext):
        return await self.tool(context, "memory_query")


@dataclass
class DeviceAgent:
    tool: DevicePort

    async def execute(self, context: TurnContext):
        if not can_execute_device_request(context.user_message):
            return None
        return await self.tool(context)


class SubAgentOrchestrator:
    def __init__(self, *, chat: ChatAgent, memory: MemoryAgent, device: DeviceAgent, task_tool: ToolPort, tasks):
        self.chat, self.memory, self.device = chat, memory, device
        self.task_tool, self.tasks = task_tool, tasks

    async def delegate(self, context: TurnContext, intent: str, *, progress: Progress | None = None):
        if context.has_image or context.image_urls:
            return "chat", None
        message = context.user_message
        if is_declined_operation(message):
            return "chat", None
        if intent in {"tool_use", "device_command", "memory_query"} and is_multistep_request(message):
            tool_context = ToolContext(context.user.user_id, context.session_id, context.turn_id, message)
            tools = await self.tasks.catalog.tools_for(tool_context)
            result = await self.tasks.execute(
                tool_context, allowed_tools=task_tool_scope(message, tools), progress=progress
            )
            return "task", {
                "name": "task_agent",
                "ok": result.ok,
                "message": result.message,
                "data": result.data,
                "deterministic": True,
            }
        if intent == "memory_query":
            return "memory", await self.memory.execute(context)
        if intent == "device_command" or can_execute_device_request(message):
            return "device", await self.device.execute(context)
        if intent == "tool_use":
            return "task", await self.task_tool(context, intent)
        return "chat", None


async def delegate_events(orchestrator, context, intent):
    """Emit progress while delegation runs; own/cancel the worker on disconnect."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=32)

    async def progress(event):
        await queue.put(event)

    async def work():
        try:
            role, result = await orchestrator.delegate(context, intent, progress=progress)
            await queue.put({"_delegation": (role, result)})
        except Exception as exc:
            await queue.put({"_failure": exc})

    worker = asyncio.create_task(work(), name=f"delegate:{context.turn_id}")
    try:
        while True:
            event = await queue.get()
            if "_failure" in event:
                raise event["_failure"]
            yield event
            if "_delegation" in event:
                break
    finally:
        if not worker.done():
            worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
