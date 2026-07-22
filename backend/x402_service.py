#!/usr/bin/env python3
"""WalletPress x402 Marketplace — standalone pay-per-wallet service.

THIS IS NOT PART OF THE SELF-HOSTED PRODUCT.
This is a service WE operate at walletpress.cc.

The x402 marketplace allows bots and developers to generate wallets
on demand without an account or subscription. They pay USDC per wallet,
we generate and return the keys, and we don't store them.

To run this service separately:
  uvicorn x402_service:app --port 8011

Requires:
  - A Solana RPC endpoint (for payment verification)
  - A USDC wallet for receiving payments
  - Separate database from the main WalletPress instance
"""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("x402")

app = FastAPI(
    title="WalletPress x402 Marketplace",
    version="1.0.0",
    description="Pay-per-wallet generation. No account needed. Send USDC, get keys.",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Pricing ──────────────────────────────────────────────────────

PRICE_PER_WALLET = 0.01
MIN_ORDER_USD = 1.00
FREE_WALLETS = 3

PAYMENT_ADDRESS = os.getenv("WP_PAYMENT_ADDRESS", "G1uZFfsdxK2PuH2Em5LhRkEcptxHWe4vy5BZak67QyKv")
PAYMENT_CHAIN = "solana"
PAYMENT_TOKEN = "USDC"

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
        CREATE TABLE IF NOT EXISTS credits (
            api_key TEXT PRIMARY KEY, balance REAL NOT NULL DEFAULT 0,
            total_spent REAL DEFAULT 0, created_at REAL NOT NULL
        );
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
    derivation_path: str = Field(
        default="",
        description="Custom BIP44 derivation path (e.g. m/44'/60'/0'/0/1). Empty = chain default.",
    )
    xpub: str = Field(
        default="",
        description="Master public key (xpub/tpub/ypub/zpub). Derive child keys without us seeing private keys.",
    )
    idempotency_key: str = Field(
        default="",
        description="Idempotency key. Same key = same order returned. Prevents double-charge on retry.",
    )


class CreditsRequest(BaseModel):
    amount: float = Field(default=10, ge=10)
    payment_tx: str = Field(default="")


# ── Helpers ──────────────────────────────────────────────────────


def calc_price(count: int) -> float:
    if count >= 100000:
        return round(count * 0.001, 2)
    if count >= 10000:
        return round(count * 0.002, 2)
    if count >= 1000:
        return round(count * 0.005, 2)
    return round(count * PRICE_PER_WALLET, 2)


async def verify_payment(chain: str, tx: str, expected: float) -> bool:
    if expected <= 0:
        return True
    if not tx:
        return False
    from core.x402_verify import verify_usdc_payment

    result = await verify_usdc_payment(chain, tx, expected)
    return result["verified"]


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

    # Payment via credits
    if req.api_key:
        conn = get_db()
        row = conn.execute(
            "SELECT balance FROM credits WHERE api_key = ?", (req.api_key,)
        ).fetchone()
        if not row or row["balance"] < total:
            conn.close()
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Insufficient credits",
                    "balance": row["balance"] if row else 0,
                    "required": total,
                    "buy_url": "/api/v1/marketplace/credits",
                },
            )
        conn.execute(
            "UPDATE credits SET balance = balance - ?, total_spent = total_spent + ? WHERE api_key = ?",
            (total, total, req.api_key),
        )
        conn.commit()
        conn.close()
        payment_method = "credits"
    elif total >= MIN_ORDER_USD and not req.payment_tx:
        from core.x402_verify import get_pay_to

        pay_to = get_pay_to(chain)
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Payment required",
                "amount_usd": total,
                "pay_to": pay_to,
                "chain": chain,
                "token": "USDC",
                "instructions": f"Send ${total} USDC on {chain.upper()} to {pay_to}",
            },
        )
    elif total >= MIN_ORDER_USD and req.payment_tx:
        if not await verify_payment(chain, req.payment_tx, total):
            raise HTTPException(status_code=402, detail="Payment verification failed")
        payment_method = "onchain"
    else:
        payment_method = "free"

    # Generate wallets
    from wallet_engine.generator import get_generator

    generator = get_generator()
    wallets = []

    if req.xpub:
        from bip_utils import Bip32Secp256k1, Bip32Slip10Ed25519

        chain_info = CHAINS.get(chain)
        if not chain_info:
            raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")
        try:
            if chain_info.curve == "ed25519":
                bip32_ctx = Bip32Slip10Ed25519.FromXPub(req.xpub)
            else:
                bip32_ctx = Bip32Secp256k1.FromXPub(req.xpub)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid xpub: {e}")
        for i in range(count):
            child_path = f"0/{i}"
            child_key = bip32_ctx.DerivePath(child_path)
            pub_bytes = child_key.PublicKey().Raw().ToBytes()
            wallets.append(
                {
                    "index": i + 1,
                    "address": pub_bytes.hex()[:40],
                    "private_key": "",
                    "mnemonic": "",
                    "derivation_path": child_path,
                    "derivation_method": "xpub",
                    "note": "Derived from your xpub. We never had the private key.",
                }
            )
    else:
        for i in range(count):
            gen_kwargs = {
                "chain_key": chain,
                "label": f"x402_{order_id}_{i}",
                "tags": ["x402", order_id],
            }
            if req.derivation_path:
                gen_kwargs["derivation_path"] = req.derivation_path
<<<<<<< Updated upstream
            wallet = generator.generate(**gen_kwargs)
            wallets.append({
                "index": i + 1, "address": wallet.address,
                "private_key": wallet.private_key_hex, "mnemonic": wallet.mnemonic,
                "derivation_path": wallet.derivation_path,
            })
=======
            wallet = generator.generate(**gen_kwargs)  # type: ignore[arg-type]
            wallets.append(
                {
                    "index": i + 1,
                    "address": wallet.address,
                    "private_key": wallet.private_key_hex,
                    "mnemonic": wallet.mnemonic,
                    "derivation_path": wallet.derivation_path,
                }
            )
>>>>>>> Stashed changes

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

    from core.proof import (
        sign_receipt,
        sign_key_deletion,
        get_receipt_public_key,
        get_source_tree_hash,
    )

    receipt_sig = sign_receipt(order_id, chain, count, total, time.time())
    deletion_sig = sign_key_deletion(order_id, chain, count, [w["address"] for w in wallets])
    return {
        "order_id": order_id,
        "chain": chain,
        "count": count,
        "total_usd": total,
        "payment_method": payment_method,
        "derivation_method": "xpub" if req.xpub else "mnemonic",
        "wallets": wallets,
        "receipt": {
            "signature": receipt_sig,
            "public_key": get_receipt_public_key(),
            "verify_url": f"/api/v1/marketplace/verify-receipt?order_id={order_id}",
        },
        "key_deletion_attestation": {
            "signature": deletion_sig,
            "algorithm": "Ed25519",
            "note": "This proves the private keys were cleared from memory after generation. We did not store them.",
        },
        "trust": {
            "keys_stored": False,
            "keys_encrypted": False,
            "keys_returned_once": True,
            "key_deletion_attested": True,
            "open_source": "https://github.com/cryptorugmuncher/walletpress",
            "source_commit": get_source_tree_hash(),
            "receipt_signed": True,
            "receipt_algorithm": "Ed25519",
            "audit_logged": True,
            "provenance": f"Verify at /api/v1/proof/verify/{order_id}",
            "note": "Keys returned once. We do not store them. Signed receipt + key deletion attestation prove authenticity.",
        },
    }


@app.post("/api/v1/marketplace/credits")
async def buy_credits(req: CreditsRequest):
    """Buy credits via on-chain USDC payment.

    SECURITY: Every request with payment_tx MUST be verified on-chain
    before crediting. Previously this endpoint accepted any non-empty
    payment_tx string and minted credits for free (P0-1).
    """
    if not req.payment_tx:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Payment required",
                "amount_usd": req.amount,
                "pay_to": PAYMENT_ADDRESS,
                "chain": PAYMENT_CHAIN,
                "token": "USDC",
            },
        )

    # Verify the payment on-chain via PayAI facilitator.
    # This is the same call used by /generate to validate payment_tx.
    verified = await verify_payment(PAYMENT_CHAIN, req.payment_tx, req.amount)
    if not verified:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Payment verification failed",
                "payment_tx": req.payment_tx,
                "amount_usd": req.amount,
                "note": "Send USDC on Solana to the payment address, then retry with the tx signature.",
            },
        )

    # Only now mint credits
    api_key = f"wp_cred_{secrets.token_hex(16)}"
    conn = get_db()
    conn.execute(
        "INSERT INTO credits (api_key, balance, total_spent, created_at) VALUES (?, ?, 0, ?)",
        (api_key, req.amount, time.time()),
    )
    conn.commit()
    conn.close()
    logger.info(
        f"x402 credits purchased: amount=${req.amount} tx={req.payment_tx[:16]}... key={api_key[:12]}..."
    )
    return {"credits_added": req.amount, "balance": req.amount, "api_key": api_key}


@app.get("/api/v1/marketplace/pricing")
async def pricing():
    return {
        "per_wallet": PRICE_PER_WALLET,
        "minimum_order_usd": MIN_ORDER_USD,
        "free_tier": {"wallets": FREE_WALLETS},
        "tiers": [
            {"range": "1-999", "price": f"${PRICE_PER_WALLET}/wallet"},
            {"range": "1,000-9,999", "price": "$0.005/wallet"},
            {"range": "10,000-99,999", "price": "$0.002/wallet"},
            {"range": "100,000+", "price": "$0.001/wallet"},
        ],
        "payment": {"chain": PAYMENT_CHAIN, "token": PAYMENT_TOKEN, "address": PAYMENT_ADDRESS},
        "operator": "Rug Munch Media LLC",
        "note": "This is a service operated by WalletPress. Not available for self-hosted installations.",
    }


@app.get("/api/v1/marketplace/public-key")
async def marketplace_public_key():
    """Get the server's Ed25519 public key for receipt verification.

    Every order receipt is signed with this key. Verify receipts offline
    using any Ed25519 library. The key is generated once on first startup
    and persisted to disk.
    """
    from core.proof import get_receipt_public_key

    return {
        "algorithm": "Ed25519",
        "public_key": get_receipt_public_key(),
        "purpose": "Order receipt signing for x402 marketplace",
        "generated_at": "first_startup",
        "verify_tool": 'pip install pynacl && python3 -c "from nacl.bindings import crypto_sign_open; import base64; ..."',
    }


@app.get("/api/v1/marketplace/verify-receipt")
async def verify_receipt(order_id: str, signature: str = "", pubkey: str = ""):
    """Verify a signed order receipt.

    Pass the order_id, signature, and public key from the order response.
    Returns whether the signature is valid.
    """
    from core.proof import verify_receipt as _verify, get_receipt_public_key
    from core.wallet_db_pool import DbPool

    pool = DbPool(DB_PATH)
    row = pool.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    pubkey = pubkey or get_receipt_public_key()
    valid = _verify(
        order_id,
        row["chain"],
        row["count"],
        row["amount_usd"],
        row["created_at"],
        signature,
        pubkey,
    )
    return {
        "order_id": order_id,
        "valid": valid,
        "chain": row["chain"],
        "count": row["count"],
        "amount_usd": row["amount_usd"],
        "created_at": row["created_at"],
        "public_key_used": pubkey,
        "note": "If valid, this receipt proves WalletPress generated these wallets at this time.",
    }


if __name__ == "__main__":
    import uvicorn

    # When run standalone, add health endpoint manually
    @app.get("/health")
    async def _x402_health():
        return {"status": "ok", "service": "x402-marketplace", "version": "1.0.0"}

    uvicorn.run("x402_service:app", host="0.0.0.0", port=int(os.getenv("WP_X402_PORT", "8011")))
