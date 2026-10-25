#!/usr/bin/env python3
"""WalletPress x402 Marketplace — pay-per-wallet, no account needed.

THIS IS A STRIPPED EDUCATIONAL EXAMPLE WITH PLACEHOLDER VALUES.
Replace all placeholder constants with your own production values.

x402 pattern: request -> verify payment via the x402-coffer facilitator ->
generate wallets and return keys -> signed receipt attesting to key deletion.

Local policy stays ABOVE the facilitator: MIN_ORDER_USD, per-client free-tier
tracking and KeyStore credit auth are enforced here, and the coffer's echoed
network/asset/amount is confirm-matched against the quoted order before keys
are returned. Fail-closed: an unreachable coffer refuses the order with 402.

Thin facade only: persistence is core.x402_store, gate policy is
core.x402_gate, RFC 7807 rendering is core.problem_details.

  uvicorn x402_service:app --port 8011
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core import x402_gate, x402_store
from core.problem_details import install_error_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("x402")

app = FastAPI(
    title="WalletPress x402 Marketplace",
    version="1.0.0",
    description="Pay-per-wallet generation. No account needed.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://rugmunch.io", "https://walletpress.rugmunch.io"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

install_error_handlers(app)

# ── Pricing (env-configurable; enforced server-side at gate time) ──

PRICE_PER_WALLET = float(os.getenv("WP_X402_PRICE_PER_WALLET", "0.01"))
MIN_ORDER_USD = float(os.getenv("WP_X402_MIN_ORDER_USD", "1.00"))
FREE_WALLETS = int(os.getenv("WP_X402_FREE_WALLETS", "3"))

PAYMENT_ADDRESS = os.getenv("WP_PAYMENT_ADDRESS", "YOUR_PAYMENT_ADDRESS_HERE")
PAYMENT_CHAIN = "solana"
PAYMENT_TOKEN = "USDC"  # noqa: S105

DB_PATH = Path(os.getenv("WP_X402_DB", "/data/x402.db"))

TRUST = {
    "keys_stored": False,
    "keys_encrypted": False,
    "keys_returned_once": True,
    "open_source": True,
    "note": "Keys returned once. We do not store them.",
}

# Gate policy is imported, not re-implemented, so the tests that patch
# xs.FREE_WALLETS / xs.MIN_ORDER_USD still own the numbers.
_verify_credits = x402_gate.verify_credits
verify_with_coffer = x402_gate.verify_with_coffer
settle_with_coffer = x402_gate.settle_with_coffer


# ── Models ───────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    chain: str = Field(default="sol", description="Chain key: sol, base, polygon, arbitrum, eth")
    count: int = Field(default=1, ge=1, le=100000)
    payment_tx: str = Field(
        default="", description="USDC tx for paid orders. Leave empty for free tier."
    )
    api_key: str = Field(
        default="", description="Prepaid API key. Alternative to per-order payment."
    )
    idempotency_key: str = Field(
        default="",
        description="Idempotency key. Same key = same order returned.",
    )


# ── Helpers ──────────────────────────────────────────────────────


def calc_price(count: int) -> float:
    """Calculate price for a given wallet count."""
    return round(count * PRICE_PER_WALLET, 2)


def _client_identity(api_key: str, client_ip: str) -> str:
    """Identity an idempotency key is scoped to (CWE-639).

    A hashed prepaid key when the caller presents one, otherwise the peer
    address. The raw key is never persisted.
    """
    if api_key:
        return "key:" + hashlib.sha256(api_key.encode()).hexdigest()[:32]
    return f"ip:{client_ip}"


def _get_free_wallets_used(client_ip: str) -> int:
    """Count free-tier wallets already issued to this client (server-verified)."""
    return x402_store.free_wallets_used(DB_PATH, client_ip)


def _record_free_usage(client_ip: str, count: int) -> None:
    """Add freshly issued free-tier wallets to this client's total."""
    x402_store.record_free_usage(DB_PATH, client_ip, count)


def _generate_wallets(chain: str, count: int, order_id: str) -> list[dict]:
    """Generate the paid-for wallets exactly once; keys stay in memory."""
    from wallet_engine.generator import get_generator

    generator = get_generator()
    wallets = []
    for i in range(count):
        wallet = generator.generate(
            chain_key=chain, label=f"x402_{order_id}_{i}", tags=["x402", order_id]
        )
        wallets.append(
            {
                "index": i + 1,
                "address": wallet.address,
                "private_key": wallet.private_key_hex,
                "mnemonic": wallet.mnemonic,
                "derivation_path": wallet.derivation_path,
            }
        )
    return wallets


# ── Endpoints ────────────────────────────────────────────────────


@app.post("/api/v1/marketplace/generate")
async def generate(req: GenerateRequest, request: Request):
    from wallet_engine.chains import CHAINS

    chain = req.chain.lower()
    if chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")

    count = min(max(req.count, 1), 100000)
    total = calc_price(count)
    client_ip = request.client.host if request.client else ""
    identity = _client_identity(req.api_key, client_ip)

    if req.idempotency_key:
        existing = x402_store.find_order_by_idempotency(
            DB_PATH, req.idempotency_key, identity
        )
        if existing:
            return {
                "idempotent": True,
                "order_id": existing["order_id"],
                "note": "Order already processed with this idempotency key",
            }

    order_id = f"x402_{secrets.token_hex(8)}"
    payment_method, settlement = await x402_gate.authorize(
        api_key=req.api_key,
        payment_tx=req.payment_tx,
        order_id=order_id,
        chain=chain,
        total_usd=total,
        price_per_wallet=PRICE_PER_WALLET,
        min_order_usd=MIN_ORDER_USD,
    )

    # Reserve BEFORE generating: quota is claimed atomically, and if anything
    # below fails the claim is released, so a failure can neither over-grant
    # nor silently burn a client's free tier. Nothing is counted after the
    # write — that is what used to double-count.
    reserved = False
    if payment_method == "free":
        reserved, free_used = x402_store.reserve_free_quota(
            DB_PATH, client_ip, count, FREE_WALLETS
        )
        if not reserved:
            raise x402_gate.free_tier_rejection(
                chain=chain,
                total_usd=total,
                free_used=free_used,
                limit=FREE_WALLETS,
                pay_to=PAYMENT_ADDRESS,
            )

    try:
        wallets = _generate_wallets(chain, count, order_id)
        x402_store.insert_order(
            DB_PATH,
            order_id=order_id,
            chain=chain,
            count=count,
            amount_usd=total,
            payment_tx=req.payment_tx,
            client_ip=client_ip,
            idempotency_key=req.idempotency_key,
            client_identity=identity,
        )
    except Exception:
        if reserved:
            x402_store.release_free_quota(DB_PATH, client_ip, count)
        logger.exception("order_failed order_id=%s chain=%s count=%s", order_id, chain, count)
        raise

    return {
        "order_id": order_id,
        "chain": chain,
        "count": count,
        "total_usd": total,
        "payment_method": payment_method,
        "wallets": wallets,
        "trust": TRUST,
        "settlement": settlement,
    }


@app.get("/api/v1/marketplace/pricing")
async def pricing():
    return {
        "per_wallet": PRICE_PER_WALLET,
        "minimum_order_usd": MIN_ORDER_USD,
        "free_tier": {"wallets": FREE_WALLETS},
        "payment": {"chain": PAYMENT_CHAIN, "token": PAYMENT_TOKEN, "address": PAYMENT_ADDRESS},
        "note": "This is a generic OSS example. Replace with your own pricing.",
    }


if __name__ == "__main__":
    import uvicorn

    @app.get("/health")
    async def _x402_health():
        return {"status": "ok", "service": "x402-marketplace", "version": "1.0.0"}

    uvicorn.run("x402_service:app", host="0.0.0.0", port=int(os.getenv("WP_X402_PORT", "8011")))  # noqa: S104
