#!/usr/bin/env python3
"""WalletPress x402 Marketplace — Educational OSS example of pay-per-wallet.

THIS IS A STRIPPED EDUCATIONAL EXAMPLE WITH PLACEHOLDER VALUES.
Replace all placeholder constants with your own production values.

The x402 marketplace allows bots and developers to generate wallets
on demand without an account or subscription. They pay per wallet,
you generate and return the keys, and you don't store them.

x402 pattern:
  1. Client requests wallet generation with payment_tx
  2. Server verifies the payment on-chain
  3. Server generates wallets and returns keys
  4. Server provides a signed receipt attesting to key deletion

To run this service separately:
  uvicorn x402_service:app --port 8011

Requires:
  - A blockchain RPC endpoint (for payment verification)
  - A wallet for receiving payments
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


# ── Pricing (REPLACE WITH YOUR OWN VALUES) ─────────────────────────

PRICE_PER_WALLET = 0.01  # TODO: Replace with your pricing
MIN_ORDER_USD = 1.00  # TODO: Minimum order in USD
FREE_WALLETS = 3  # TODO: Free tier limit

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


async def verify_payment(chain: str, tx: str, expected: float) -> bool:
    """Verify an on-chain payment via the PayAI facilitator.

    Delegates to ``core.x402_verify.verify_usdc_payment()`` for multi-chain
    USDC verification (Solana, Base, Polygon, Arbitrum, Ethereum).

    Returns True if payment is verified, False otherwise.
    """
    if expected <= 0:
        return True
    if not tx:
        return False
    try:
        from core.x402_verify import verify_usdc_payment

        result = await verify_usdc_payment(chain, tx, expected)
        if not result.get("verified", False):
            logger.warning(f"Payment verification failed: {result.get('reason', 'unknown')}")
            return False
        return True
    except ImportError:
        logger.error("x402 verification module not available")
        return False
    except Exception as e:
        logger.error(f"Payment verification error: {e}")
        return False  # CONSERVATIVE: don't approve unverified payments


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

    # Determine payment method
    if total >= MIN_ORDER_USD and not req.payment_tx:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Payment required",
                "amount_usd": total,
                "pay_to": PAYMENT_ADDRESS,
                "chain": chain,
                "token": "USDC",
                "instructions": f"Send ${total} USDC on {chain.upper()} to {PAYMENT_ADDRESS}",
            },
        )
    elif total >= MIN_ORDER_USD and req.payment_tx:
        if not await verify_payment(chain, req.payment_tx, total):
            raise HTTPException(status_code=402, detail="Payment verification failed")
        payment_method = "onchain"
    elif req.api_key:
        # In production: verify API key has sufficient credits
        payment_method = "credits"
    else:
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
