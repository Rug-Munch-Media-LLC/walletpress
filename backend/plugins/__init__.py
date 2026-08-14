"""WalletPress Protocol Plugins — extend agent with any blockchain protocol."""

from __future__ import annotations

# Auto-discover and register all plugin modules
import importlib
import pkgutil

import plugins
from plugins.sdk import (
    WalletPressPlugin,
    _plugins as _plugin_registry,
    execute_plugin_tool,
    get_all_tools,
    list_plugins,
    register_plugin,
)


def _discover_plugins():
    for _, modname, ispkg in pkgutil.iter_modules(plugins.__path__):
        if modname != "sdk" and not ispkg:
            importlib.import_module(f"plugins.{modname}")


_discover_plugins()

__all__ = [
    "WalletPressPlugin",
    "_plugins",
    "execute_plugin_tool",
    "get_all_tools",
    "list_plugins",
    "register_plugin",
]
