"""WalletPress Plugin SDK — Protocol plugins for the AI Wallet Agent.

Extend the agent with any blockchain protocol. Plugins register MCP-style
tools that the agent can call. Patterns:
  - DEX: swap_tokens, add_liquidity, remove_liquidity
  - Lending: deposit, withdraw, borrow, repay
  - NFT: mint, buy, sell, list
  - Bridge: bridge_tokens, get_bridge_quotes
  - Prediction Markets: bet, resolve, claim

Usage:
    from plugins.sdk import WalletPressPlugin, register_plugin

    class MyPlugin(WalletPressPlugin):
        name = "myplugin"
        description = "My custom protocol"

        def tools(self) -> list[dict]:
            return [{"name": "my_tool", "description": "...", "parameters": {...}}]

        async def execute(self, tool: str, params: dict) -> dict:
            return {"result": "ok"}

    register_plugin(MyPlugin())
"""

from __future__ import annotations

import logging
from typing import ClassVar

logger = logging.getLogger("wp.plugins")


class WalletPressPlugin:
    """Base class for WalletPress protocol plugins.

    Each plugin provides MCP-style tools that the agent can call.
    Plugins are auto-discovered and registered at startup.
    """

    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    # Chain families this plugin works with
    supported_chains: ClassVar[list[str]] = ["evm", "solana"]

    def tools(self) -> list[dict]:
        """Return the tools this plugin provides.

        Each tool is a dict with:
          name: str — tool name (snake_case)
          description: str — what the tool does
          parameters: dict — JSON Schema for parameters
          required: list[str] — required parameter names
        """
        return []

    async def execute(self, tool: str, params: dict) -> dict:
        """Execute a tool with the given parameters.

        Args:
            tool: Tool name (must match a tool from tools())
            params: Parameters matching the tool's schema

        Returns:
            dict with results
        """
        raise NotImplementedError(f"Plugin {self.name} has no execute handler")

    def on_load(self):
        """Called when the plugin is loaded. Use for setup."""

    def on_unload(self):
        """Called when the plugin is unloaded. Use for cleanup."""


# ── Plugin Registry ──────────────────────────────────────────────────────────

_plugins: dict[str, WalletPressPlugin] = {}


def register_plugin(plugin: WalletPressPlugin):
    """Register a plugin with the agent."""
    if not plugin.name:
        raise ValueError("Plugin must have a name")
    _plugins[plugin.name] = plugin
    plugin.on_load()
    logger.info(f"Plugin loaded: {plugin.name} v{plugin.version}")


def get_plugin(name: str) -> WalletPressPlugin | None:
    """Get a plugin by name."""
    return _plugins.get(name)


def list_plugins() -> list[dict]:
    """List all registered plugins with their tools."""
    result = []
    for name, plugin in _plugins.items():
        result.append(
            {
                "name": name,
                "description": plugin.description,
                "version": plugin.version,
                "supported_chains": plugin.supported_chains,
                "tools": [t["name"] for t in plugin.tools()],
            }
        )
    return result


def get_all_tools() -> list[dict]:
    """Get ALL tools from ALL registered plugins."""
    tools = []
    for plugin in _plugins.values():
        tools.extend(plugin.tools())
    return tools


async def execute_plugin_tool(plugin_name: str, tool: str, params: dict) -> dict:
    """Execute a tool on a specific plugin."""
    plugin = _plugins.get(plugin_name)
    if not plugin:
        return {"error": f"Plugin '{plugin_name}' not found"}
    try:
        return await plugin.execute(tool, params)
    except NotImplementedError:
        return {"error": f"Tool '{tool}' not implemented by plugin '{plugin_name}'"}
    except Exception as e:
        logger.error(f"Plugin {plugin_name} tool {tool} failed: {e}")
        return {"error": f"Plugin error: {e}"}
