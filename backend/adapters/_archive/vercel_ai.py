"""Vercel AI SDK Adapter — Use WalletPress tools with Vercel AI SDK."""

from __future__ import annotations


def get_tools() -> list[dict]:
    """Get all MCP tools as Vercel AI SDK tool format."""
    from agent.mcp_server import mcp

    tools = {}
    for t in mcp._tool_manager.list_tools():
        tools[t.name] = {
            "description": t.description or t.name,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string"} for k in (t.parameters or {})},
            },
        }
    return tools
