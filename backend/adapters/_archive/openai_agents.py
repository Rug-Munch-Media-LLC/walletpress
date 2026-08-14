"""OpenAI Agents SDK Adapter — Use WalletPress tools with OpenAI Agents SDK."""

from __future__ import annotations


def get_tools() -> list[dict]:
    """Get all MCP tools as OpenAI function-calling format."""
    from agent.mcp_server import mcp

    functions = []
    for t in mcp._tool_manager.list_tools():
        functions.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or t.name,
                    "parameters": {
                        "type": "object",
                        "properties": {k: {"type": "string"} for k in (t.parameters or {})},
                        "required": list((t.parameters or {}).keys())[:3] if t.parameters else [],
                    },
                },
            }
        )
    return functions
