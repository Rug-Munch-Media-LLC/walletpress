"""Application lifespan: startup validation, service wiring, background tasks.

Deferred imports are intentional: services are loaded only when the app starts,
which keeps import time fast and avoids importing crypto machinery in tooling
that merely inspects the app object.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from core.config import cfg

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("wp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate config, wire services into app.state, run background tasks."""
    logger.info(f"WalletPress v{cfg.version} starting on {cfg.host}:{cfg.port}")

    if not cfg.admin_key:
        raise RuntimeError("WP_ADMIN_KEY is required. Set it in the environment before starting.")
    if not cfg._vault_password:
        raise RuntimeError(
            "WP_VAULT_PASSWORD is required. Set it in the environment before starting."
        )

    os.makedirs(cfg.data_dir, exist_ok=True)

    from agent.providers import list_providers

    for line in list_providers().split("\n"):
        logger.info(line)

    from plugins.defi import REF_HYPERLIQUID_WALLET, REF_JUPITER_WALLET, REVENUE_MODE

    jup_ok = bool(REF_JUPITER_WALLET)
    hl_ok = bool(REF_HYPERLIQUID_WALLET)
    logger.info(
        f"Revenue mode: {REVENUE_MODE.upper()} | Jupiter: {'READY (50bps)' if jup_ok else 'NEEDS SETUP'} | Hyperliquid: {'READY (builder code)' if hl_ok else 'NEEDS SETUP'}"
    )
    if REVENUE_MODE == "freemium":
        logger.info(
            "Revenue: Jupiter 50bps (set WP_REF_JUPITER_WALLET) + Hyperliquid builder fees (set WP_REF_HYPERLIQUID_WALLET, needs 100 USDC perps)"
        )
    else:
        logger.info("Self-referral mode: you keep 100% of platform revenue.")

    from core.audit import AuditLog
    from core.auth import KeyStore
    from core.license import LicenseManager
    from core.proof import ProofOfGeneration
    from core.vault import Vault
    from core.webhooks import get_webhook_deliverer
    from wallet_engine.generator import WalletGenerator

    app.state.vault = Vault(cfg.db_path)
    app.state.key_store = KeyStore(cfg.keys_path)
    app.state.audit = AuditLog(cfg.audit_path)
    app.state.license = LicenseManager()
    app.state.proof = ProofOfGeneration(cfg.data_dir / "proof.db")
    app.state.generator = WalletGenerator(vault_password=cfg.vault_password)
    app.state.webhook_deliverer = get_webhook_deliverer()
    await app.state.webhook_deliverer.start()

    from routers._persistent_store import PersistentStore

    PersistentStore.reload_webhooks()

    if os.getenv("WP_POF_ARWEAVE_KEY_PATH"):
        from core.proof import anchor_source_commit

        result = anchor_source_commit()
        if result.get("anchored"):
            logger.info(
                f"Source commit anchored: {result['commit'][:16]}... tx={result.get('tx_id', '')}"
            )
        else:
            logger.warning(f"Source commit anchoring skipped: {result.get('reason', 'unknown')}")

    from agent.scheduler import scheduler as agent_scheduler

    agent_scheduler.start()
    logger.info("AI Wallet Agent scheduler started")

    async def proof_auto_commit_loop():
        if os.getenv("WP_POF_AUTO_COMMIT", "1") != "1":
            logger.info("Proof of Generation auto-commit disabled (WP_POF_AUTO_COMMIT=0)")
            return
        interval = int(os.getenv("WP_POF_COMMIT_INTERVAL", "3600"))
        await asyncio.sleep(interval)
        while True:
            try:
                from core.proof import get_proof

                proof = get_proof()
                root_hash, count = proof.compute_merkle_root()
                if root_hash:
                    chain = "local"
                    if os.getenv("WP_POF_ARWEAVE_KEY_PATH"):
                        chain = "arweave"
                    elif os.getenv("WP_POF_ETH_RPC") and os.getenv("WP_POF_ETH_PRIVATE_KEY"):
                        chain = "ethereum"
                    proof.commit(root_hash, count, commitment_chain=chain)
                    logger.info(
                        f"Auto-committed {count} attestations to {chain}: {root_hash[:16]}..."
                    )
            except Exception as e:
                logger.error(f"Proof auto-commit failed: {e}")
            await asyncio.sleep(interval)

    app.state.proof_commit_task = asyncio.ensure_future(proof_auto_commit_loop())

    async def temporal_cleanup_loop():
        while True:
            await asyncio.sleep(60)
            try:
                from routers.chain_vault import _cleanup_expired_temporals

                _cleanup_expired_temporals()
            except Exception as e:
                logger.error(f"Temporal cleanup failed: {e}")

    app.state.temporal_cleanup_task = asyncio.ensure_future(temporal_cleanup_loop())

    yield

    agent_scheduler.stop()
    await app.state.webhook_deliverer.stop()
    logger.info("WalletPress shutdown complete")
