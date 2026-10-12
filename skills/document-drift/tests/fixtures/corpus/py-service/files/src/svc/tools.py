"""The MCP tools over the store."""
from __future__ import annotations

from mcp.types import Tool

TOOLS = [
    Tool(
        name="store.put",
        description="Save a value under a key.",
        inputSchema={"type": "object",
                     "properties": {"key": {"type": "string"}, "value": {"type": "string"}}},
    ),
    Tool(
        name="store.get",
        description="Read the value saved under a key.",
        inputSchema={"type": "object", "properties": {"key": {"type": "string"}}},
    ),
    Tool(
        name="store.list",
        description="List every stored key (maintenance only).",
        inputSchema={"type": "object", "properties": {}},
    ),
]
