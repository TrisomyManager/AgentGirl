"""Official MCP stdio bridge. Trusted host identity is fixed at launch.

python mcp_actions_server.py --user-id local-user --session-id local-session
"""

import argparse
import asyncio
import logging
import sys

import structlog

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))

from mcp.server.lowlevel import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import TextContent, Tool  # noqa: E402

from action_executor import handlers  # noqa: E402, F401
from action_executor.registry import get_registry  # noqa: E402
from shared_runtime.database import close_database, init_database_schema  # noqa: E402


async def serve(user_id: str, session_id: str):
    registry = get_registry()
    server = Server("companion-actions")

    @server.list_tools()
    async def list_tools():
        return [Tool.model_validate(meta) for meta in registry.mcp_tools()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        result = await registry.dispatch_contextual(name, arguments, user_id=user_id, session_id=session_id)
        from mcp.types import CallToolResult

        return CallToolResult(
            isError=not result.ok,
            content=[TextContent(type="text", text=result.message)],
            structuredContent={"ok": result.ok, "data": result.data},
        )

    await init_database_schema()
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        await close_database()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--session-id", default="mcp")
    args = parser.parse_args()
    if not args.user_id.strip():
        parser.error("user-id must not be empty")
    asyncio.run(serve(args.user_id, args.session_id))
