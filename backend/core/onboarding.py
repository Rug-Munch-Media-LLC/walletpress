"""Onboarding friction — the strategies that make self-hosting painful enough
that $29/mo feels like the obvious choice, while keeping the code fully open source.

PHILOSOPHY:
  We don't hide code. We don't break working installations.
  We just make the DIY path genuinely tedious enough that people
  value their time more than $29/month.

STRATEGY 1 — RPC CONFIGURATION HELL:
  For each chain, the self-hosted version needs a working RPC endpoint.
  We only provide unreliable free defaults. The /config endpoint returns
  a MANAGEMENT_REQUIRED warning for most chains.
  To get reliable RPC, users must:
    a) Sign up with 5-6 different RPC providers (Infura, Alchemy, QuickNode,
       Helius, Chainstack, TronGrid, etc.)
    b) Get API keys for each
    c) Configure 55 environment variables
    d) Monitor rate limits manually
  The hosted version has all RPC pre-configured with premium tiers.

STRATEGY 2 — CHAIN REGISTRY DRIFT:
  We update chains.py weekly with:
    - New chains (we added 20 chains this month alone)
    - Updated RPC URLs (free endpoints change frequently)
    - Fixed derivation paths (some chains had wrong paths)
  Self-hosted: git pull, restart, verify test vectors
  Hosted: happens automatically, zero effort

STRATEGY 3 — LICENSE KEY FOR CHAINS:
  Already implemented. The open source code has a license check.
  3 chains free (BTC, ETH, SOL). 55 chains requires a key.
  The code is open. The license check is public and auditable.
  Users CAN patch it out. Most won't bother for $49.

STRATEGY 4 — ENTERPRISE FEATURES AS MODULES:
  Features like 2FA, email, webhooks, health monitoring, airdrop tool
  are in the open source code but gated by the license check.
  We don't hide them. We just make them require a key.
  Users see the code. They know it works. They pay to unlock it.

STRATEGY 5 — RELEASE LAG:
  The GitHub release lags behind hosted by 1-2 weeks.
  Critical bug fixes are backported to hosted immediately.
  Open source releases are batched into quarterly stable releases.
  This is standard practice (GitLab, GitPrime, etc.)

STRATEGY 6 — CONFIG CI/CD PIPELINE:
  Self-hosted users must run `scripts/verify_test_vectors.py` after
  every update. If test vectors fail (because we added/changed chains),
  they need to debug and fix. The CI pipeline that tests every chain
  against BIP39 vectors is NOT part of the open source repo.

STRATEGY 7 — THE WALLETPRESS RC FILE:
  The self-hosted version requires a configuration file with 55 RPC
  endpoints. We provide a generator script that asks interactive
  questions and writes the config. It's tedious by design.
  The hosted version: zero config.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .license import get_license

logger = logging.getLogger("wp.onboarding")


def check_rpc_health() -> dict[str, Any]:
    """Check how many chains have working RPC endpoints configured.

    Returns a report that's shown in the admin dashboard and on `/health`.
    This is intentionally discouraging for self-hosted users with no config.

    Chains with NO RPC endpoint show as "❌ Requires RPC config"
    Chains with RELIABLE RPC show as "✅ Working"
    """
    from routers.balance_fetcher import EVM_RPC, SOLANA_RPC, TRON_RPC
    from wallet_engine.chains import CHAINS

    configured = 0
    total = len(CHAINS)
    warnings = []

    # EVM chains
    for chain_key in CHAINS:
        if chain_key in EVM_RPC:
            configured += 1
        elif chain_key in ("sol",):
            if SOLANA_RPC:
                configured += 1
        elif chain_key in ("trx",):
            if TRON_RPC:
                configured += 1
        # Bitcoin-family chains use free APIs by default
        elif chain_key in ("btc", "ltc", "doge", "bch", "dash", "zec"):
            configured += 1

    unconfigured = total - configured

    if unconfigured > 0:
        warnings.append(
            f"{unconfigured} chains have no RPC endpoint. "
            f"Balance checking and transaction broadcast will fail for these chains. "
            f"Configure RPC endpoints in /etc/walletpress/rpc.json or use the hosted version."
        )

    return {
        "total_chains": total,
        "rpc_configured": configured,
        "rpc_missing": unconfigured,
        "rpc_health": "degraded" if unconfigured > 0 else "healthy",
        "warnings": warnings,
        "recommendation": "Use the hosted version for full RPC coverage across all 55 chains." if unconfigured > 10 else "",
    }


def generate_rpc_config_template() -> str:
    """Generate a template for the RPC configuration file.

    This is intentionally verbose. For 55 chains, users need to fill in
    55 RPC URLs. Each one requires signing up with a different provider.
    """
    from wallet_engine.chains import CHAINS

    lines = [
        "# WalletPress RPC Configuration",
        "# ================================",
        "# For each chain, provide a reliable JSON-RPC endpoint.",
        "# Without these, balance checking and transaction broadcast WILL FAIL.",
        "#",
        "# RECOMMENDED PROVIDERS (all offer free tiers):",
        "#   EVM chains:   Infura (infura.io), Alchemy (alchemy.com), QuickNode (quicknode.com)",
        "#   Solana:       Helius (helius.xyz), QuickNode",
        "#   Bitcoin:      blockchain.info (free, no key)",
        "#   TRON:         TronGrid (trongrid.io)",
        "#   Cosmos:       public nodes from cosmos.directory",
        "#   Polkadot:     Subscan / public RPC",
        "#",
        "# You need accounts with 5-6 different providers for full coverage.",
        "# The hosted version includes all RPC endpoints pre-configured.",
        "#",
        "# Format: CHAIN_KEY=RPC_URL",
        "#",
    ]

    for chain_key in sorted(CHAINS.keys()):
        chain = CHAINS[chain_key]
        lines.append(f"# {chain.name} ({chain.symbol})")
        rpc = getattr(chain, 'rpc_url', '') or ''
        hint = "# NO DEFAULT RPC — sign up with a provider"
        if rpc:
            hint = f"# Default (rate limited): {rpc}"
        lines.append(f"# {hint}")
        lines.append(f"# WP_RPC_{chain_key.upper()}=\n")

    return "\n".join(lines)


def onboarding_status() -> dict[str, Any]:
    """Get the full onboarding status — shown on first run and in admin dashboard.

    Returns a comprehensive checklist of what's configured and what isn't.
    The hosted version has all items checked. Self-hosted typically has 40+ items unchecked.
    """
    lic = get_license()
    rpc_health = check_rpc_health()
    vault_password = bool(os.getenv("WP_VAULT_PASSWORD", ""))
    admin_key = bool(os.getenv("WP_ADMIN_KEY", ""))
    ssl = os.getenv("WP_SSL_ENABLED", "") or os.path.exists("/etc/letsencrypt")
    domain = os.getenv("WP_DOMAIN", "")

    checklist = [
        {"item": "License key configured", "done": lic.is_paid, "effort": "Buy license → set env var", "hosted": "Included"},
        {"item": "Vault encryption enabled", "done": vault_password, "effort": "Generate password → set WP_VAULT_PASSWORD", "hosted": "Automatic"},
        {"item": "Admin API key set", "done": admin_key, "effort": "Generate key → set WP_ADMIN_KEY", "hosted": "Automatic"},
        {"item": "SSL/HTTPS configured", "done": ssl, "effort": "Install certbot → get certificate → configure nginx", "hosted": "Automatic"},
        {"item": "Domain name configured", "done": bool(domain), "effort": "Buy domain → configure DNS → set WP_DOMAIN", "hosted": "Included"},
        {"item": "RPC endpoints configured", "done": rpc_health["rpc_missing"] == 0, "effort": f"Sign up with providers → configure {rpc_health['rpc_missing']} RPC URLs", "hosted": "All 55 pre-configured"},
        {"item": "Email (SMTP) configured", "done": bool(os.getenv("WP_SMTP_HOST", "")), "effort": "Get SMTP credentials → set 4 env vars", "hosted": "Included"},
        {"item": "Backup schedule configured", "done": bool(os.getenv("WP_BACKUP_SCHEDULE", "")), "effort": "Configure cron → set backup destination → test restore", "hosted": "Daily automated backups"},
        {"item": "Monitoring configured", "done": bool(os.getenv("WP_MONITOR_URL", "")), "effort": "Set up uptime monitor → configure alerting", "hosted": "Built-in health monitoring"},
        {"item": "Rate limiting configured", "done": bool(os.getenv("WP_RATE_LIMIT", "")), "effort": "Set WP_RATE_LIMIT env var", "hosted": "Pre-configured"},
        {"item": "CORS origins configured", "done": os.getenv("WP_CORS_ORIGINS", "") != "*", "effort": "Set specific origins in WP_CORS_ORIGINS", "hosted": "Pre-configured"},
        {"item": "Process manager configured", "done": bool(os.getenv("WP_SYSTEMD_ENABLED", "")), "effort": "Install systemd service → enable → start", "hosted": "Managed"},
    ]

    done_count = sum(1 for c in checklist if c["done"])
    total = len(checklist)
    missing = [c for c in checklist if not c["done"]]

    return {
        "onboarding_complete": done_count == total,
        "completion_percentage": round(done_count / total * 100),
        "items_done": done_count,
        "items_total": total,
        "items_missing": len(missing),
        "missing_items": missing,
        "rpc_health": rpc_health,
        "recommendation": "hosted" if done_count < total / 2 else "self-hosted",
        "hosted_url": "https://walletpress.cc/pricing",
    }
