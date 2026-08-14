"""Eliza OS Adapter (plugin) — Use WalletPress tools from Eliza agents."""
from __future__ import annotations

# Eliza plugins import via: https://github.com/elizaos/eliza/tree/main/packages/plugin-goat
# This adapter provides the Eliza-compatible tool format for WalletPress.

def get_actions() -> list[dict]:
    """Get MCP tools as Eliza action format."""
    from agent.mcp_server import mcp
    actions = []
    for t in mcp._tool_manager.list_tools():
        actions.append({
            "name": t.name,
            "description": t.description or t.name,
            "similes": [t.name.replace("_", " ")],
            "supports_async": True,
            "handler": lambda params, tool=t: _handle(tool.name, params),
        })
    return actions

def _handle(tool_name: str, params: dict) -> dict:
    import asyncio

    from agent.mcp_server import mcp
    for t in mcp._tool_manager.list_tools():
        if t.name == tool_name:
            if asyncio.iscoroutinefunction(t.fn):
                return asyncio.run(t.fn(**params))
            return t.fn(**params)
    return {"error": f"Tool {tool_name} not found"}
