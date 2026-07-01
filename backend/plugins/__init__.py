"""WalletPress Protocol Plugins — extend agent with any blockchain protocol."""
from plugins.sdk import WalletPressPlugin, register_plugin, list_plugins, get_all_tools, execute_plugin_tool
from plugins.sdk import _plugins as _plugin_registry

# Auto-discover and register all plugin modules
import importlib
import pkgutil
import plugins

def _discover_plugins():
    for importer, modname, ispkg in pkgutil.iter_modules(plugins.__path__):
        if modname != "sdk" and not ispkg:
            importlib.import_module(f"plugins.{modname}")

_discover_plugins()

__all__ = [
    "WalletPressPlugin",
    "register_plugin",
    "list_plugins",
    "get_all_tools",
    "execute_plugin_tool",
    "_plugins",
]
