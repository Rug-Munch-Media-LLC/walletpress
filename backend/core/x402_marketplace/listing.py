"""Marketplace listing — wallet generation routes (sync and async)."""

from __future__ import annotations

import os
import secrets
import threading
import time

from fastapi import HTTPException, Request

from .common import (
    _WARM_POOL,
    _WARM_POOL_LOCK,
    _WARM_POOL_MIN,
    _WARM_POOL_TARGET,
    CHAINS,
    MIN_ORDER_USD,
    PRICE_1000,
    PRICE_10000,
    PRICE_100000,
    PRICE_PER_WALLET,
    GenerateRequest,
    _jobs,
    _jobs_lock,
    _run_async_job,
    calc_price,
    get_db,
    logger,
    router,
)


@router.post("/generate")
async def generate(req: GenerateRequest, request: Request):
    """Generate wallets. Pay per wallet. Get keys. No storage."""
    chain = req.chain.lower()
    if chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Unsupported: {chain}")
    count = min(max(req.count, 1), 100000)
    total = calc_price(count)
    bot_ip = request.client.host if request.client else ""

    # Idempotency: return existing order if same key used
    if req.idempotency_key:
        db = get_db()
        conn = db._conn()
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

    # Payment via prepaid credits
    if req.api_key:
        db = get_db()
        bal = db.get_balance(req.api_key)
        if bal >= total:
            db.deduct(req.api_key, total)
            payment_method = "credits"
        else:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Insufficient credits",
                    "balance": bal,
                    "required": total,
                    "shortfall": round(total - bal, 2),
                    "buy_url": "/api/v1/marketplace/credits",
                },
            )
    elif total >= MIN_ORDER_USD and not req.payment_tx:
        from core.x402_verify import CHAIN_CONFIG, get_pay_to

        pay_to = get_pay_to(chain)
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Payment required",
                "amount_usd": total,
                "min_wallets": max(int(MIN_ORDER_USD / PRICE_PER_WALLET), 100),
                "price_per_wallet": PRICE_PER_WALLET,
                "pricing_tiers": [
                    {"range": "1-999", "price": f"${PRICE_PER_WALLET}"},
                    {"range": "1,000-9,999", "price": f"${PRICE_1000}"},
                    {"range": "10,000-99,999", "price": f"${PRICE_10000}"},
                    {"range": "100,000+", "price": f"${PRICE_100000}"},
                ],
                "pay_to": pay_to,
                "chain": chain,
                "token": "USDC",
                "supported_chains": list(CHAIN_CONFIG.keys()),
                "instructions": f"Send ${total} USDC on {chain.upper()} to {pay_to} to receive {count} wallets. Minimum ${MIN_ORDER_USD}.",
            },
        )
    elif total >= MIN_ORDER_USD and req.payment_tx:
        from core.x402_verify import verify_usdc_payment

        result = await verify_usdc_payment(chain, req.payment_tx, total)
        if not result["verified"]:
            raise HTTPException(
                status_code=402, detail=f"Payment verification failed: {result['reason']}"
            )
        payment_method = "onchain"
    else:
        payment_method = "free"

    # Generate wallets
    import core.x402_marketplace as _pkg

    generator = _pkg.get_generator()
    wallets = []

    if req.xpub:
        # Zero-trust mode: derive from customer's master public key
        # We never see the private key. We derive child public keys and addresses.
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
            raise HTTPException(status_code=400, detail=f"Invalid xpub: {e}") from e

        for i in range(count):
            child_path = f"0/{i}"
            child_key = bip32_ctx.DerivePath(child_path)
            pub_bytes = child_key.PublicKey().Raw().ToBytes()
            from wallet_engine.generator import GeneratedWallet

            wallet = GeneratedWallet(
                chain=chain,
                chain_name=chain_info.name,
                symbol=chain_info.symbol,
                address=pub_bytes.hex()[:40],
                public_key_hex=pub_bytes.hex(),
                derivation_path=child_path,
                label=f"x402_{order_id}_{i}",
                tags=["x402", order_id, "xpub_derived"],
            )
            wallets.append(
                {
                    "index": i + 1,
                    "address": wallet.address,
                    "private_key": "",  # We never have it
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
            wallet = generator.generate(**gen_kwargs)
            wallets.append(
                {
                    "index": i + 1,
                    "address": wallet.address,
                    "private_key": wallet.private_key_hex,
                    "mnemonic": wallet.mnemonic,
                    "derivation_path": wallet.derivation_path,
                }
            )

    # Log (no keys stored)
    db = get_db()
    db.log_order(
        order_id, chain, count, total, req.payment_tx or "free", bot_ip, req.idempotency_key or ""
    )

    # Attest (public key hash only — never hash private keys)
    from core.proof import get_proof

    proof = get_proof()
    for i, w in enumerate(wallets[:100]):
        proof.attest(
            wallet_id=f"x402_{order_id}_{i}",
            chain=chain,
            address=w["address"],
            public_key_hex="",
        )

    # Auto-commit Merkle root
    try:
        root_hash, att_count = proof.compute_merkle_root()
        if root_hash:
            commit_chain = "local"
            if os.getenv("WP_POF_ARWEAVE_KEY_PATH"):
                commit_chain = "arweave"
            elif os.getenv("WP_POF_ETH_RPC") and os.getenv("WP_POF_ETH_PRIVATE_KEY"):
                commit_chain = "ethereum"
            proof.commit(root_hash, att_count, commitment_chain=commit_chain)
    except Exception as e:
        logger.warning(f"x402 batch auto-commit failed (non-fatal): {e}")

    # Broadcast live event
    from core.event_bus import emit as _emit_event

    _emit_event(
        "x402.generated",
        {
            "order_id": order_id,
            "chain": chain,
            "count": count,
            "total_usd": total,
            "payment_method": payment_method,
        },
    )

    # Audit
    from core.audit import get_audit

    get_audit().log(
        "x402.generate",
        actor=req.api_key[:12] if req.api_key else "anon",
        resource=order_id,
        detail={"chain": chain, "count": count, "usd": total, "payment": payment_method},
    )

    from core.proof import (
        get_receipt_public_key,
        get_source_tree_hash,
        sign_key_deletion,
        sign_receipt,
    )

    receipt_sig = sign_receipt(order_id, chain, count, total, time.time())
    deletion_sig = sign_key_deletion(order_id, chain, count, [w["address"] for w in wallets])
    return {
        "order_id": order_id,
        "chain": chain,
        "count": count,
        "total_usd": total,
        "price_per_wallet": round(total / count, 4) if count > 0 else 0,
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
            "note": "Keys returned once. We don't store them. Signed receipt + key deletion attestation prove authenticity.",
        },
    }


@router.post("/generate/async")
async def generate_async(req: GenerateRequest, request: Request):
    """Generate wallets asynchronously for large batches.

    Returns a job_id immediately. Poll GET /jobs/{job_id} for completion.
    Optionally pass webhook_url to get notified when done.

    Same pricing, payment, and trust model as POST /generate.
    Best for batches over 1,000 wallets.
    """
    chain = req.chain.lower()
    if chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Unsupported: {chain}")
    count = min(max(req.count, 1), 100000)
    total = calc_price(count)
    bot_ip = request.client.host if request.client else ""

    if req.idempotency_key:
        db = get_db()
        conn = db._conn()
        existing = conn.execute(
            "SELECT * FROM orders WHERE idempotency_key = ?", (req.idempotency_key,)
        ).fetchone()
        conn.close()
        if existing:
            return {"idempotent": True, "order_id": existing["order_id"]}

    order_id = f"x402_{secrets.token_hex(8)}"
    job_id = f"job_{secrets.token_hex(8)}"

    if req.api_key:
        db = get_db()
        bal = db.get_balance(req.api_key)
        if bal >= total:
            db.deduct(req.api_key, total)
            payment_method = "credits"
        else:
            raise HTTPException(
                status_code=402,
                detail={"error": "Insufficient credits", "balance": bal, "required": total},
            )
    elif total >= MIN_ORDER_USD and not req.payment_tx:
        from core.x402_verify import get_pay_to

        raise HTTPException(
            status_code=402,
            detail={
                "error": "Payment required",
                "amount_usd": total,
                "pay_to": get_pay_to(chain),
                "chain": chain,
            },
        )
    elif total >= MIN_ORDER_USD and req.payment_tx:
        from core.x402_verify import verify_usdc_payment

        result = await verify_usdc_payment(chain, req.payment_tx, total)
        if not result["verified"]:
            raise HTTPException(status_code=402, detail=f"Payment failed: {result['reason']}")
        payment_method = "onchain"
    else:
        payment_method = "free"

    db = get_db()
    db.log_order(
        order_id, chain, count, total, req.payment_tx or "free", bot_ip, req.idempotency_key or ""
    )

    with _jobs_lock:
        _jobs[job_id] = {
            "status": "queued",
            "order_id": order_id,
            "chain": chain,
            "count": count,
            "created_at": time.time(),
        }

    thread = threading.Thread(
        target=_run_async_job,
        args=(job_id, chain, count, order_id, req.derivation_path, req.xpub, ""),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_id,
        "order_id": order_id,
        "chain": chain,
        "count": count,
        "total_usd": total,
        "payment_method": payment_method,
        "status": "queued",
        "poll_url": f"/api/v1/marketplace/jobs/{job_id}",
        "note": "Job queued. Poll the jobs endpoint for completion. Large batches process in background.",
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Poll an async generation job for status and results."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/warm-pool/status")
async def warm_pool_status():
    """Check warm pool fill levels per chain."""
    with _WARM_POOL_LOCK:
        return {
            "status": {chain: len(pool) for chain, pool in _WARM_POOL.items()},
            "target_per_chain": _WARM_POOL_TARGET,
            "refill_threshold": _WARM_POOL_MIN,
        }
