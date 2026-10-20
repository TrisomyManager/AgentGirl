"""Synthetic official MCP server for transport integration tests."""

import sys

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

server = FastMCP(
    "synthetic-test", host="127.0.0.1", port=int(sys.argv[2]) if len(sys.argv) > 2 else 8000, log_level="WARNING"
)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def add(a: int, b: int) -> int:
    return a + b


@server.tool()
def change(value: str) -> str:
    return value


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def who(user_id: str) -> str:
    return user_id


if __name__ == "__main__":
    server.run(transport=sys.argv[1] if len(sys.argv) > 1 else "stdio")
