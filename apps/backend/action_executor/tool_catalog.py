"""One callable catalog for local and host-approved external tools."""

from __future__ import annotations

from dataclasses import dataclass

from action_executor.mcp_client import MCPHub, mcp_hub
from action_executor.plugins import PluginCallContext, PluginManager, plugin_manager
from action_executor.registry import ActionRegistry, ActionResult, get_registry


@dataclass(frozen=True)
class ToolContext:
    user_id: str
    session_id: str = ""
    turn_id: str = ""
    raw_text: str = ""


class ToolCatalog:
    def __init__(
        self,
        registry: ActionRegistry | None = None,
        external: MCPHub | None = None,
        plugins: PluginManager | None = None,
    ):
        self.registry = registry if registry is not None else get_registry()
        self.external = external if external is not None else mcp_hub
        self.plugins = plugins if plugins is not None else plugin_manager

    async def tools_for(self, context: ToolContext) -> list[dict]:
        local = self.registry.mcp_tools()
        remote = await self.external.tools_for(context.user_id)
        tools = local + remote + self.plugins.tools_for(context.user_id)
        if len({item["name"] for item in tools}) != len(tools):
            raise ValueError("Local and external tool names collide")
        return tools

    async def call(self, name: str, arguments: dict, context: ToolContext, *, operation_id: str = "") -> ActionResult:
        if self.plugins.owns(name):
            return await self.plugins.call(
                name,
                arguments,
                PluginCallContext(
                    context.user_id,
                    context.session_id,
                    context.turn_id,
                    operation_id,
                ),
            )
        if self.registry.has(name):
            return await self.registry.dispatch_contextual(
                name,
                arguments,
                user_id=context.user_id,
                session_id=context.session_id,
                turn_id=context.turn_id,
                raw_text=context.raw_text,
                operation_id=operation_id,
            )
        return await self.external.call(
            name,
            arguments,
            user_id=context.user_id,
            session_id=context.session_id,
            turn_id=context.turn_id,
            operation_id=operation_id,
        )
