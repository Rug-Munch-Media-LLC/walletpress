"""Transport for walletpress-mcp: remote REST proxy or in-process calls.

Both call paths live here so the MCP tool surface in walletpress_mcp.py stays
under the fleet 200-line file cap. Import is side-effect-light: it only reads
WP_API_URL / WP_API_KEY / WALLETPRESS_BACKEND and records the mode.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("wp.mcp.standalone")

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

        required = (
            "core.vault",
            "wallet_engine.chains",
            "wallet_engine.generator",
            "core.config",
        )
        if not all(importlib.util.find_spec(module) for module in required):
            return {
                "error": "Cannot import wallet engine. Set WALLETPRESS_BACKEND or use WP_API_URL."
            }
        return _local_call(method, path, data)


def _local_call(method: str, path: str, _data: dict | None = None) -> dict:
    """Handle a local call by routing to the appropriate module."""
    from core.vault import get_vault
    from wallet_engine.chains import CHAINS

    vault = get_vault()

    if path == "/health":
        return {"status": "ok", "mode": "local", "service": "walletpress-mcp"}
    if "/api/v1/chain-vault/chains" in path:
        return {
            "total_chains": len(CHAINS),
            "chains": {
                k: {"name": v.name, "symbol": v.symbol} for k, v in CHAINS.items()
            },
        }
    if "/api/v1/chain-vault/vault" in path and method == "GET":
        wallets = vault.list(limit=100)
        return {
            "wallets": [
                {"id": w.id, "chain": w.chain, "address": w.address, "label": w.label}
                for w in wallets
            ]
        }
    if "/api/v1/chain-vault/stats" in path:
        return vault.stats()
    if "/api/v1/chain-vault/healthz" in path:
        return {"status": "ok"}
    return {"error": f"No local handler for {method} {path}"}
