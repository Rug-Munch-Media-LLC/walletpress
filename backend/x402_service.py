#!/usr/bin/env python3
"""WalletPress x402 Marketplace — Educational OSS example of pay-per-wallet.

THIS IS A STRIPPED EDUCATIONAL EXAMPLE WITH PLACEHOLDER VALUES.
Replace all placeholder constants with your own production values.

The x402 marketplace allows bots and developers to generate wallets
on demand without an account or subscription. They pay per wallet,
you generate and return the keys, and you don't store them.

x402 pattern:
  1. Client requests wallet generation with payment_tx
  2. Server verifies the payment via the x402-coffer facilitator
  3. Server generates wallets and returns keys
  4. Server provides a signed receipt attesting to key deletion

Payment verification is delegated to a self-hosted x402-coffer instance
(``X402_FACILITATOR_URL``) configured with the treasury receiving wallets —
the in-house on-chain verification stubs were removed. Local policy stays
ABOVE the facilitator: MIN_ORDER_USD, per-client free-tier tracking and
KeyStore credit auth are enforced here, and the coffer's echoed
network/asset/amount is confirm-matched against the quoted order before keys
are returned (mirroring the pry-scraper billing confirm flow). Fail-closed:
if the coffer is unreachable the order is refused with HTTP 402.

To run this service separately:
  uvicorn x402_service:app --port 8011

Requires:
  - A reachable x402-coffer facilitator (X402_FACILITATOR_URL)
  - Separate database from the main application instance
"""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import coffer_client

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

# ── RFC 7807 Error Handlers ─────────────────────────────────────────
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """RFC 7807 Problem Details for HTTP errors."""
    rid = getattr(request.state, "request_id", "-")
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    status = exc.status_code
    titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
    }
    return JSONResponse(
        status_code=status,
        content={
            "type": "/errors/not_found" if status == 404 else "about:blank",
            "title": titles.get(status, "Error"),
            "status": status,
            "detail": detail,
            "request_id": rid,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unhandled exceptions."""
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        return await http_exception_handler(request, exc)
    rid = getattr(request.state, "request_id", "-")
    logger.exception("unhandled_exception request_id=%s path=%s", rid, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "Internal server error",
            "request_id": rid,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


# ── Pricing (env-configurable; enforced server-side at gate time) ──

PRICE_PER_WALLET = float(os.getenv("WP_X402_PRICE_PER_WALLET", "0.01"))
MIN_ORDER_USD = float(os.getenv("WP_X402_MIN_ORDER_USD", "1.00"))
FREE_WALLETS = int(os.getenv("WP_X402_FREE_WALLETS", "3"))

PAYMENT_ADDRESS = os.getenv("WP_PAYMENT_ADDRESS", "YOUR_PAYMENT_ADDRESS_HERE")
PAYMENT_CHAIN = "solana"
PAYMENT_TOKEN = "USDC"  # noqa: S105

# ── Database ─────────────────────────────────────────────────────

DB_PATH = Path(os.getenv("WP_X402_DB", "/data/x402.db"))


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY, chain TEXT NOT NULL,
            count INTEGER NOT NULL, amount_usd REAL NOT NULL,
            payment_tx TEXT DEFAULT '', payment_status TEXT DEFAULT 'pending',
            status TEXT DEFAULT 'pending', created_at REAL NOT NULL,
            client_ip TEXT DEFAULT '',
            idempotency_key TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_orders_idempotency ON orders(idempotency_key);
    """)
    conn.commit()
    return conn


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
    """Calculate price for a given wallet count.

    In production, implement volume discounts and tiered pricing here.
    """
    return round(count * PRICE_PER_WALLET, 2)


def _get_free_wallets_used(client_ip: str) -> int:
    """Count free-tier wallets already issued to this client (server-verified)."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS free_tier_usage (
            client_ip TEXT PRIMARY KEY, wallets INTEGER NOT NULL DEFAULT 0
        );
    """)
    row = conn.execute(
        "SELECT COALESCE(SUM(wallets), 0) FROM free_tier_usage WHERE client_ip = ?",
        (client_ip,),
    ).fetchone()
    conn.close()
    return int(row[0]) if row and row[0] else 0


def _record_free_usage(client_ip: str, count: int):
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS free_tier_usage (
            client_ip TEXT PRIMARY KEY, wallets INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.execute(
        "INSERT INTO free_tier_usage (client_ip, wallets) VALUES (?, ?) "
        "ON CONFLICT(client_ip) DO UPDATE SET wallets = wallets + ?",
        (client_ip, count, count),
    )
    conn.commit()
    conn.close()


def _verify_credits(api_key: str) -> bool:
    """Server-verify a prepaid API key against the local KeyStore.

    Client-supplied claims are never trusted: the key must exist (unhashed)
    in the server-side key store for the credits payment method to apply.
    """
    if not api_key:
        return False
    try:
        from core.auth import get_key_store

        return get_key_store().verify(api_key) is not None
    except Exception:
        logger.exception("Credit verification failed")
        return False


async def verify_with_coffer(order_id: str, chain: str, tx: str, expected_usd: float) -> dict:
    """Verify a reported on-chain payment via the x402-coffer facilitator.

    Returns the coffer verification dict (``verified: True/False`` plus echo
    fields). Fail-closed: raises ``coffer_client.CofferUnavailable`` when the
    coffer is unreachable or ``X402_FACILITATOR_URL`` is unset, so the caller
    refuses the order with HTTP 402 rather than trusting the client.
    """
    if expected_usd <= 0:
        return {"verified": True, "reason": "free", "network": "", "asset": ""}
    if not tx:
        return {"verified": False, "reason": "No payment tx provided"}
    network, asset = coffer_client.resolve_network_asset(chain)
    logger.info(
        "coffer_verify_start order_id=%s chain=%s expected_usd=%s",
        order_id,
        chain,
        expected_usd,
    )
    return await coffer_client.verify_payment(
        payment_id=order_id,
        tx_hash=tx,
        network=network,
        asset=asset,
        amount_usd=expected_usd,
    )


async def settle_with_coffer(
    order_id: str, chain: str, tx: str, expected_usd: float
) -> dict | None:
    """Best-effort settlement of a verified payment (EIP-3009 authorizations).

    Called only AFTER :func:`verify_with_coffer` confirmed the payment. The
    verify gate is authoritative (funds already reached the coffer-managed
    treasury); settlement failures are logged, never a reason to withhold an
    order whose payment is verified. Returns the settlement dict or None.
    """
    try:
        network, asset = coffer_client.resolve_network_asset(chain)
        return await coffer_client.settle_payment(
            payment_id=order_id,
            tx_hash=tx,
            network=network,
            asset=asset,
            amount_usd=expected_usd,
        )
    except coffer_client.CofferUnavailable:
        logger.warning(
            "coffer_settle_unavailable order_id=%s — verify already passed; fulfilling",
            order_id,
        )
        return None


# ── Endpoints ────────────────────────────────────────────────────


@app.post("/api/v1/marketplace/generate")
async def generate(req: GenerateRequest, request: Request):
    chain = req.chain.lower()
    from wallet_engine.chains import CHAINS

    if chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")

    count = min(max(req.count, 1), 100000)
    total = calc_price(count)
    client_ip = request.client.host if request.client else ""

    # Idempotency: return existing order if same key used
    if req.idempotency_key:
        conn = get_db()
        existing = conn.execute(
            "SELECT * FROM orders WHERE idempotency_key = ?", (req.idempotency_key,)
        ).fetchone()
        conn.close()
        if existing:
            return {
                "idempotent": True,
                "order_id": existing["order_id"],
                "note": "Order already processed with this idempotency key",
            }

    order_id = f"x402_{secrets.token_hex(8)}"
    settlement: dict | None = None

    # ── Payment gate (server-enforced, per route) ──────────────────
    # 1. Minimum order size is enforced unconditionally — no client can
    #    bypass it by omitting payment info or claiming credits.
    if total < MIN_ORDER_USD:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Order below minimum",
                "required_min_usd": MIN_ORDER_USD,
                "requested_usd": total,
                "hint": f"Increase wallet count to at least {max(1, int(-(-MIN_ORDER_USD // PRICE_PER_WALLET)))} wallets.",
            },
        )

    # 2. Determine payment method with server-side verification.
    if req.api_key:
        # Credits: the API key must be verified server-side. Invalid keys
        # are rejected — we never trust a client-asserted credit balance.
        if not _verify_credits(req.api_key):
            raise HTTPException(status_code=402, detail="Invalid or unknown prepaid API key")
        payment_method = "credits"
    elif req.payment_tx:
        # On-chain: gate on the coffer facilitator. MIN_ORDER_USD above is
        # local policy enforced BEFORE the facilitator is consulted. Fail
        # closed (402) if the coffer is unreachable — never fulfill on an
        # unverifiable payment.
        try:
            verification = await verify_with_coffer(order_id, chain, req.payment_tx, total)
        except coffer_client.CofferUnavailable as exc:
            logger.error("Coffer verification unavailable for order %s: %s", order_id, exc)
            raise HTTPException(
                status_code=402,
                detail="Payment verification unavailable — please retry shortly",
            ) from exc
        except ValueError as exc:  # unsupported payment chain
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not verification.get("verified"):
            raise HTTPException(
                status_code=402,
                detail=f"Payment verification failed: {verification.get('reason') or 'not verified'}",
            )
        # Confirm-match mirror (parity with pry-scraper billing): the coffer's
        # echoed network/asset/amount must match the quoted order before keys
        # are returned.
        network, asset = coffer_client.resolve_network_asset(chain)
        ok, match_reason = coffer_client.confirm_matches_order(
            verification, network=network, asset=asset, amount_usd=total
        )
        if not ok:
            logger.warning("Coffer confirm-match failed for order %s: %s", order_id, match_reason)
            raise HTTPException(
                status_code=402,
                detail=f"Payment verification failed: {match_reason}",
            )
        payment_method = "onchain"
        settlement = await settle_with_coffer(order_id, chain, req.payment_tx, total)
    else:
        # Free tier: enforced against server-tracked per-client usage.
        free_used = _get_free_wallets_used(client_ip)
        if free_used + count > FREE_WALLETS:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Payment required",
                    "reason": f"Free tier exhausted ({free_used}/{FREE_WALLETS} wallets used)",
                    "amount_usd": total,
                    "pay_to": PAYMENT_ADDRESS,
                    "chain": chain,
                    "token": "USDC",
                    "instructions": f"Send ${total} USDC on {chain.upper()} to {PAYMENT_ADDRESS}",
                },
            )
        payment_method = "free"

    # Generate wallets
    from wallet_engine.generator import get_generator

    generator = get_generator()
    wallets = []

    for i in range(count):
        wallet = generator.generate(
            chain_key=chain,
            label=f"x402_{order_id}_{i}",
            tags=["x402", order_id],
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

    conn = get_db()
    conn.execute(
        "INSERT INTO orders (order_id, chain, count, amount_usd, payment_tx, payment_status, status, created_at, client_ip, idempotency_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            order_id,
            chain,
            count,
            total,
            req.payment_tx or "free",
            "confirmed",
            "completed",
            time.time(),
            client_ip,
            req.idempotency_key or "",
        ),
    )
    conn.commit()
    conn.close()

    if payment_method == "free":
        _record_free_usage(client_ip, count)

    return {
        "order_id": order_id,
        "chain": chain,
        "count": count,
        "total_usd": total,
        "payment_method": payment_method,
        "wallets": wallets,
        "trust": {
            "keys_stored": False,
            "keys_encrypted": False,
            "keys_returned_once": True,
            "open_source": True,
            "note": "Keys returned once. We do not store them.",
        },
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
