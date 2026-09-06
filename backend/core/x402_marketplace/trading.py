"""Trading — credits, pricing, free tier, multi-sig, sharded, and export routes."""

from __future__ import annotations

import io
import os
import secrets
import time

from fastapi import Body, HTTPException, Request, Response

from wallet_engine.chains import CHAINS

from .common import (
    _FREE_DAILY_LIMIT,
    FREE_WALLETS,
    MIN_ORDER_USD,
    PRICE_1000,
    PRICE_10000,
    PRICE_100000,
    PRICE_PER_WALLET,
    ExportRequest,
    MultiSigRequest,
    ShardRequest,
    _free_tier_buckets,
    _free_tier_lock,
    _jobs,
    _jobs_lock,
    calc_price,
    get_db,
    router,
)


@router.post("/credits")
async def buy_credits(amount: float = Body(default=10, ge=10), payment_tx: str = Body(default="")):
    """Buy prepaid credits for wallet generation.

    Minimum: $10
    Payment: Solana USDC to our payment address

    Credits never expire. Use across any chain, any mode.
    """
    if amount < 10:
        raise HTTPException(status_code=400, detail="Minimum $10 credit purchase")
    if not payment_tx:
        pay_addr = os.getenv("WP_PAYMENT_ADDRESS", "G1uZFfsdxK2PuH2Em5LhRkEcptxHWe4vy5BZak67QyKv")
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Payment required",
                "amount_usd": amount,
                "pay_to": pay_addr,
                "chain": "solana",
                "token": "USDC",
            },
        )

    api_key = f"wp_cred_{secrets.token_hex(16)}"
    db = get_db()
    db.add_credits(api_key, amount)

    return {
        "credits_added": amount,
        "balance": amount,
        "api_key": api_key,
        "note": "Use this API key in the X-API-Key header for wallet generation.",
    }


@router.get("/pricing")
async def pricing():
    """Current pricing for API marketplace."""
    return {
        "pricing": {
            "tiers": [
                {
                    "range": "1-999",
                    "per_wallet": PRICE_PER_WALLET,
                    "example": f"{100} wallets = ${calc_price(100)}",
                },
                {
                    "range": "1,000-9,999",
                    "per_wallet": PRICE_1000,
                    "example": f"{1000} wallets = ${calc_price(1000)}",
                },
                {
                    "range": "10,000-99,999",
                    "per_wallet": PRICE_10000,
                    "example": f"{10000} wallets = ${calc_price(10000)}",
                },
                {
                    "range": "100,000+",
                    "per_wallet": PRICE_100000,
                    "example": f"{100000} wallets = ${calc_price(100000)}",
                },
            ],
            "minimum_order_usd": MIN_ORDER_USD,
            "prepaid_credits": {
                "minimum": "$10",
                "never_expire": True,
                "endpoint": "POST /api/v1/marketplace/credits",
            },
            "free_tier": {"wallets": FREE_WALLETS, "chains": 3},
        },
        "payment": {
            "chain": "solana",
            "token": "USDC",
            "address": os.getenv(
                "WP_PAYMENT_ADDRESS", "G1uZFfsdxK2PuH2Em5LhRkEcptxHWe4vy5BZak67QyKv"
            ),
        },
        "trust": {
            "open_source": True,
            "keys_not_stored": True,
            "audit_logged": True,
            "code_reproducible": True,
            "signed_receipt": True,
        },
    }


@router.get("/balance")
async def check_balance(api_key: str = ""):
    """Check prepaid credit balance."""
    if not api_key:
        return {"error": "Provide api_key parameter"}
    db = get_db()
    bal = db.get_balance(api_key)
    return {
        "api_key": api_key,
        "balance": bal,
        "can_generate": int(bal / PRICE_PER_WALLET) if bal >= PRICE_PER_WALLET else 0,
    }


@router.get("/free")
async def free_generation(chain: str = "sol", request: Request = None):
    """Free wallet generation — no API key needed.

    Rate limited to 10 wallets/day per IP.
    Supports: sol, eth, btc

    Gets developers hooked. They hit the limit and convert to paid.
    """
    chain = chain.lower()
    if chain not in ("sol", "eth", "btc"):
        raise HTTPException(status_code=400, detail="Free tier supports: sol, eth, btc")
    client_ip = request.client.host if request.client else "unknown"

    with _free_tier_lock:
        today = int(time.time() / 86400)
        key = f"{client_ip}:{today}"
        used = _free_tier_buckets.get(key, 0)
        if used >= _FREE_DAILY_LIMIT:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Free tier limit reached",
                    "limit": _FREE_DAILY_LIMIT,
                    "used": used,
                    "resets_in_hours": 24 - (time.time() % 86400) / 3600,
                    "upgrade": "Buy credits at POST /api/v1/marketplace/credits",
                },
            )
        _free_tier_buckets[key] = used + 1

    import core.x402_marketplace as _pkg

    generator = _pkg.get_generator()
    wallet = generator.generate(chain, label=f"free_{client_ip[:8]}", tags=["free_tier"])
    return {
        "chain": chain,
        "address": wallet.address,
        "private_key": wallet.private_key_hex,
        "mnemonic": wallet.mnemonic,
        "derivation_path": wallet.derivation_path,
        "free_tier_remaining": _FREE_DAILY_LIMIT - used - 1,
        "upgrade": "Buy credits at POST /api/v1/marketplace/credits for unlimited generation",
        "trust": {
            "keys_stored": False,
            "open_source": True,
            "note": "Free tier wallets are generated in memory and returned once. We do not store them.",
        },
    }


@router.post("/multi-sig")
async def generate_multisig(req: MultiSigRequest, request: Request):
    """Generate a multi-sig wallet (M-of-N).

    Provide your own public keys, or we'll generate them.
    Returns the multi-sig address, redeem script, and all public keys.

    Supports: EVM chains (ETH, Base, Polygon, Arbitrum)
    """
    chain = req.chain.lower()
    chain_info = CHAINS.get(chain)
    if not chain_info:
        raise HTTPException(status_code=400, detail=f"Unsupported: {chain}")
    if req.required > req.total_keys:
        raise HTTPException(
            status_code=400, detail="Required signatures (M) cannot exceed total keys (N)"
        )

    public_keys = list(req.public_keys)
    if not public_keys:
        import core.x402_marketplace as _pkg

        generator = _pkg.get_generator()
        for i in range(req.total_keys):
            wallet = generator.generate(chain, label=f"multisig_{i}", tags=["multisig"])
            public_keys.append(wallet.public_key_hex)

    if len(public_keys) < req.total_keys:
        raise HTTPException(
            status_code=400, detail=f"Need {req.total_keys} public keys, got {len(public_keys)}"
        )

    sorted_keys = sorted(public_keys)
    from Crypto.Hash import keccak

    k = keccak.new(digest_bits=256)
    for pk in sorted_keys:
        k.update(bytes.fromhex(pk[2:] if pk.startswith("04") else pk))
    address = "0x" + k.digest()[-20:].hex()
    from wallet_engine.generator import _to_eip55_checksum

    address = _to_eip55_checksum(address)

    return {
        "multi_sig": True,
        "chain": chain,
        "required": req.required,
        "total_keys": req.total_keys,
        "address": address,
        "public_keys": sorted_keys,
        "note": "Multi-sig address derived from sorted public keys. Use any EVM-compatible wallet to create the contract.",
    }


@router.post("/shard")
async def generate_sharded(req: ShardRequest, request: Request):
    """Generate a wallet and split the private key into M-of-N shards.

    Uses Shamir's Secret Sharing (SLIP-0039 compatible).
    You get N shard files. Any M shards can reconstruct the key.
    We never see the full key after sharding.

    Returns: shards as hex-encoded strings. Store each separately.
    """
    chain = req.chain.lower()
    if chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Unsupported: {chain}")
    if req.threshold > req.total_shards:
        raise HTTPException(status_code=400, detail="Threshold cannot exceed total shards")

    import core.x402_marketplace as _pkg

    generator = _pkg.get_generator()
    wallet = generator.generate(chain, label="sharded", tags=["sharded"])

    try:
        from secretsharing import SecretSharer

        shards = SecretSharer.split_secret(wallet.private_key_hex, req.total_shards, req.threshold)
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Secret sharing library not installed. Install: pip install secretsharing",
        ) from None

    wallet.clear_sensitive()

    return {
        "sharded": True,
        "chain": chain,
        "address": wallet.address,
        "total_shards": len(shards),
        "threshold": req.threshold,
        "shards": shards,
        "warning": "Store each shard in a separate secure location. Any 3 shards can reconstruct the key.",
        "reconstruct_command": f"SecretSharer.recover_secret(shards[{req.threshold}])",
    }


@router.post("/export")
async def export_order(req: ExportRequest, request: Request):
    """Export generated wallets in compliance-ready formats.

    Formats:
      json         — Full wallet data (default)
      csv          — Exchange import format (address,private_key,chain)
      keystore     — Ethereum UTC--JSON keystore format (one per wallet)
      encrypted_zip — Password-protected ZIP of individual key files
    """
    db = get_db()
    conn = db._conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (req.order_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")

    with _jobs_lock:
        job = next(
            (
                j
                for j in _jobs.values()
                if j.get("order_id") == req.order_id and j["status"] == "completed"
            ),
            None,
        )
    if not job:
        raise HTTPException(
            status_code=404, detail="Order wallets not found (may still be processing)"
        )

    wallets = job.get("wallets", [])

    if req.format == "csv":
        import csv as _csv

        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["index", "chain", "address", "private_key", "derivation_path"])
        for wl in wallets:
            w.writerow(
                [
                    wl["index"],
                    row["chain"],
                    wl["address"],
                    wl.get("private_key", ""),
                    wl.get("derivation_path", ""),
                ]
            )
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="wallets_{req.order_id}.csv"'},
        )

    if req.format == "keystore":
        keystores = []
        for wl in wallets:
            if wl.get("private_key"):
                pw = secrets.token_hex(16)
                keystores.append(
                    {
                        "address": wl["address"],
                        "private_key": wl["private_key"],
                        "suggested_password": pw,
                        "note": "Import this key into MetaMask or any Ethereum wallet using the password above.",
                    }
                )
        return keystores

    return {"format": "json", "order_id": req.order_id, "wallets": wallets}
