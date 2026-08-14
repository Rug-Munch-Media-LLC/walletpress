"""walletpress-mcp — Standalone MCP Server for WalletPress.

Connects to any WalletPress backend and exposes all wallet operations
as MCP tools. Works with any MCP client: opencode, Claude Code, Cursor,
Kilo Code, VS Code, and more.

Two modes:
  1. REMOTE — connects to a WalletPress API server (api_url + api_key)
  2. LOCAL — imports wallet engine directly (must be on same machine)

Quick start:
    # Remote mode (connect to existing WalletPress instance)
    walletpress-mcp --api-url http://localhost:8010 --api-key wp_...

    # Local mode (embed in WalletPress backend)
    python -m walletpress_mcp

    # Connect from any MCP client:
    #   opencode → Add MCP server: "walletpress-mcp"
    #   Claude Code → mcp add walletpress-mcp
"""

from __future__ import annotations

import json
import logging
import os

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("wp.mcp.standalone")
mcp = FastMCP("WalletPress Agent", log_level="WARNING")


# ── Try local mode first (direct import) ──────────────────────────────────────
BACKEND_URL = os.getenv("WP_API_URL", "")
BACKEND_KEY = os.getenv("WP_API_KEY", "")

if BACKEND_URL and BACKEND_KEY:
    # Remote mode — proxy via REST API
    _mode = "remote"
    logger.info(f"Remote mode: {BACKEND_URL}")
else:
    # Local mode — import wallet engine
    _mode = "local"
    logger.info("Local mode: importing wallet engine")
    import sys

    backend_path = os.getenv("WALLETPRESS_BACKEND", "")
    if backend_path:
        sys.path.insert(0, backend_path)


def _call_backend(method: str, path: str, data: dict | None = None) -> dict:
    """Call the WalletPress backend (remote or local)."""
    if _mode == "remote":
        import httpx

        headers = {"X-API-Key": BACKEND_KEY, "Content-Type": "application/json"}
        url = f"{BACKEND_URL.rstrip('/')}{path}"
        if method == "GET":
            r = httpx.get(url, headers=headers, timeout=15)
        else:
            r = httpx.post(url, headers=headers, json=data or {}, timeout=15)
        if r.status_code >= 400:
            return {"error": f"Backend {r.status_code}: {r.text[:200]}"}
        return r.json()
    else:
        # Local — import and call directly
        import importlib.util

        if not (
            importlib.util.find_spec("core.vault")
            and importlib.util.find_spec("wallet_engine.chains")
            and importlib.util.find_spec("wallet_engine.generator")
            and importlib.util.find_spec("core.config")
        ):
            return {"error": "Cannot import wallet engine. Set WALLETPRESS_BACKEND or use WP_API_URL."}
        return _local_call(method, path, data)


def _local_call(method: str, path: str, data: dict | None = None) -> dict:
    """Handle a local call by routing to the appropriate module."""
    from core.vault import get_vault
    from wallet_engine.chains import CHAINS

    vault = get_vault()

    if path == "/health":
        return {"status": "ok", "mode": "local", "service": "walletpress-mcp"}
    if "/api/v1/chain-vault/chains" in path:
        return {
            "total_chains": len(CHAINS),
            "chains": {k: {"name": v.name, "symbol": v.symbol} for k, v in CHAINS.items()},
        }
    if "/api/v1/chain-vault/vault" in path and method == "GET":
        wallets = vault.list(limit=100)
        return {"wallets": [{"id": w.id, "chain": w.chain, "address": w.address, "label": w.label} for w in wallets]}
    if "/api/v1/chain-vault/stats" in path:
        return vault.stats()
    if "/api/v1/chain-vault/healthz" in path:
        return {"status": "ok"}
    return {"error": f"No local handler for {method} {path}"}


# ── MCP Tool Definitions ─────────────────────────────────────────────────────


@mcp.tool()
def vault_list(chain: str = "", limit: int = 50) -> list[dict]:
    """List wallets in the vault."""
    result = _call_backend("GET", f"/api/v1/chain-vault/vault?chain={chain}&limit={limit}")
    return result.get("wallets", result) if isinstance(result, dict) else result


@mcp.tool()
def vault_stats() -> dict:
    """Get vault statistics."""
    return _call_backend("GET", "/api/v1/chain-vault/stats")


@mcp.tool()
def chains_list() -> dict:
    """List all supported chains."""
    return _call_backend("GET", "/api/v1/chain-vault/chains")


@mcp.tool()
def wallet_generate(chain: str, label: str = "", count: int = 1) -> dict:
    """Generate wallets."""
    return _call_backend("POST", "/api/v1/chain-vault/generate", {"chain": chain, "label": label, "count": count})


@mcp.tool()
def wallet_delete(wallet_id: str) -> dict:
    """Delete a wallet."""
    return _call_backend("DELETE", f"/api/v1/chain-vault/vault/{wallet_id}")


@mcp.tool()
def balance_check(chain: str, address: str) -> dict:
    """Check wallet balance."""
    return _call_backend("GET", f"/api/v1/chain-vault/validate/{chain}/{address}")


@mcp.tool()
def validate_address(chain: str, address: str) -> dict:
    """Validate an address format."""
    from wallet_engine.chains import CHAINS, validate_address as va

    chain_info = CHAINS.get(chain.lower())
    if not chain_info:
        return {"error": f"Unsupported chain: {chain}"}
    valid = va(chain, address)
    return {"chain": chain, "address": address, "valid": valid}


@mcp.tool()
def health() -> dict:
    """Check if the backend is connected."""
    return _call_backend("GET", "/health")


@mcp.tool()
def plugins_list() -> list[dict]:
    """List all registered protocol plugins."""
    try:
        from plugins.sdk import list_plugins

        return list_plugins()
    except ImportError:
        return [{"note": "Plugin system not available in standalone mode"}]


@mcp.tool()
def plugin_execute(plugin: str, tool: str, params: str) -> dict:
    """Execute a plugin tool. Params should be JSON string."""
    try:
        from plugins.sdk import execute_plugin_tool
        import asyncio

        p = json.loads(params) if isinstance(params, str) else params
        return asyncio.run(execute_plugin_tool(plugin, tool, p))
    except ImportError:
        return {"error": "Plugin system not available"}


# ── CLI Entry Point ──────────────────────────────────────────────────────────


def main():
    """Run the MCP server as a standalone CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="WalletPress MCP Server")
    parser.add_argument("--api-url", help="WalletPress API URL (remote mode)")
    parser.add_argument("--api-key", help="WalletPress API key")
    parser.add_argument("--backend-path", help="Path to walletpress backend (local mode)")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse"], help="MCP transport")
    parser.add_argument("--port", type=int, default=8080, help="Port for SSE transport")
    args = parser.parse_args()

    if args.api_url:
        os.environ["WP_API_URL"] = args.api_url
    if args.api_key:
        os.environ["WP_API_KEY"] = args.api_key
    if args.backend_path:
        os.environ["WALLETPRESS_BACKEND"] = args.backend_path

    # Re-initialize with CLI args
    global BACKEND_URL, BACKEND_KEY, _mode
    BACKEND_URL = os.getenv("WP_API_URL", "")
    BACKEND_KEY = os.getenv("WP_API_KEY", "")
    _mode = "remote" if BACKEND_URL and BACKEND_KEY else "local"

    if args.transport == "sse":
        import uvicorn

        app = mcp.sse_app()
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
