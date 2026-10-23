"""Smoke test for the walletpress-mcp tool surface.

The MCP surface is a public contract: MCP clients (opencode, Claude Code,
Cursor) bind to these names. This test pins the surface so dead-code cleanup
cannot silently rename or drop a tool.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="walletpress-mcp requires the MCP SDK")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXPECTED_TOOLS = {
    "balance_check",
    "chains_list",
    "health",
    "plugin_execute",
    "plugins_list",
    "validate_address",
    "vault_list",
    "vault_stats",
    "wallet_delete",
    "wallet_generate",
}


@pytest.fixture(scope="module")
def tools() -> list:
    """Return the registered MCP tools exactly as a client sees them."""
    import walletpress_mcp

    return asyncio.run(walletpress_mcp.mcp.list_tools())


def test_tool_names_match_contract(tools: list) -> None:
    """tools/list must expose exactly the documented tool names."""
    names = {tool.name for tool in tools}
    assert names == EXPECTED_TOOLS


def test_every_tool_is_documented_and_schema_typed(tools: list) -> None:
    """Every tool needs a description and an input schema for clients to call it."""
    for tool in tools:
        assert tool.description, f"{tool.name} has no description"
        assert isinstance(tool.inputSchema, dict), f"{tool.name} has no input schema"
        assert tool.inputSchema.get("type") == "object", (
            f"{tool.name} schema is not an object"
        )
