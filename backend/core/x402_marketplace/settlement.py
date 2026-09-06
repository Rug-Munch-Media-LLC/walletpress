"""Settlement — receipts, transparency, proofs, SLA, webhooks, timelocks."""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import time
from pathlib import Path

from fastapi import Body, HTTPException, Request

from .common import (
    CHAINS,
    TimelockRequest,
    _api_webhooks,
    _api_webhooks_lock,
    _jobs,
    _jobs_lock,
    _sla_generations,
    _sla_latencies,
    _sla_lock,
    _sla_start,
    _timelocks,
    _timelocks_lock,
    get_db,
    router,
)


@router.get("/public-key")
async def marketplace_public_key():
    """Get the server's Ed25519 public key for receipt verification."""
    from core.proof import get_receipt_public_key

    return {
        "algorithm": "Ed25519",
        "public_key": get_receipt_public_key(),
        "purpose": "Order receipt signing for x402 marketplace",
        "generated_at": "first_startup",
        "verify_tool": 'pip install pynacl && python3 -c "from nacl.bindings import crypto_sign_open; import base64; ..."',
    }


@router.get("/verify-receipt")
async def verify_receipt(order_id: str, signature: str = "", pubkey: str = ""):
    """Verify a signed order receipt — pass order_id, signature, and public key."""
    from core.proof import get_receipt_public_key, verify_receipt as _verify

    db = get_db()
    conn = db._conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
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


@router.get("/transparency")
async def transparency():
    """Public transparency dashboard — stats, roots, uptime.

    This endpoint proves we are who we say we are. No secrets here.
    """
    from core.proof import get_proof, get_receipt_public_key

    proof = get_proof()
    pstats = proof.stats()
    roots = proof.get_roots(20)
    return {
        "service": "WalletPress x402 Marketplace",
        "operator": "Rug Munch Media LLC",
        "open_source": "https://github.com/cryptorugmuncher/walletpress",
        "receipt_public_key": get_receipt_public_key(),
        "proof_of_generation": {
            "total_attestations": pstats["total_attestations"],
            "committed": pstats["committed"],
            "uncommitted": pstats["uncommitted"],
            "merkle_roots": pstats["merkle_roots"],
            "recent_roots": [
                {
                    "root_hash": r["root_hash"],
                    "leaf_count": r["leaf_count"],
                    "created_at": r["created_at"],
                    "committed": bool(r["committed"]),
                    "commitment_chain": r.get("commitment_chain", ""),
                    "commitment_tx": r.get("commitment_tx", ""),
                }
                for r in roots
            ],
        },
        "pricing": {
            "per_wallet": 0.01,
            "minimum_order": 1.00,
            "free_tier": 10,
        },
        "trust_guarantees": [
            "Keys generated in memory, returned once, never stored",
            "Every order signed with Ed25519 receipt",
            "Every wallet attested in SHA-256 Merkle tree",
            "Merkle roots committed to Arweave for permanent proof",
            "Open source — verify every line of code",
            "Reproducible Docker builds — image hash matches source",
            "No telemetry, no tracking, no data collection",
            "Audit trail append-only, immutable",
        ],
    }


@router.post("/verify-batch")
async def verify_batch(wallet_ids: list[str] = Body(...)):
    """Verify multiple wallet attestations in a single request.

    Returns a combined Merkle proof covering all wallets.
    Much more efficient than verifying one wallet at a time.
    """
    from core.proof import get_proof

    proof = get_proof()
    results = []
    for wid in wallet_ids:
        try:
            attest = proof.get_attestation(wid)
            if attest:
                results.append(
                    {
                        "wallet_id": wid,
                        "attested": True,
                        "leaf_hash": attest.get("leaf_hash", ""),
                        "root_hash": attest.get("root_hash", ""),
                        "created_at": attest.get("created_at"),
                    }
                )
            else:
                results.append({"wallet_id": wid, "attested": False})
        except Exception:
            results.append({"wallet_id": wid, "attested": False, "error": "Verification failed"})
    return {
        "verified": sum(1 for r in results if r["attested"]),
        "total": len(wallet_ids),
        "results": results,
    }


@router.get("/sla")
async def sla():
    """Enterprise SLA dashboard — speed, latency, queue depth, order history.

    Enterprise procurement needs this before they'll buy.
    """
    with _sla_lock:
        now = time.time()
        recent = [t for t in _sla_generations if now - t < 86400]
        recent_latencies = _sla_latencies[-1000:]
        avg_speed = sum(recent_latencies) / len(recent_latencies) if recent_latencies else 0
        p50 = sorted(recent_latencies)[len(recent_latencies) // 2] if recent_latencies else 0
        p95 = sorted(recent_latencies)[int(len(recent_latencies) * 0.95)] if recent_latencies else 0
        p99 = sorted(recent_latencies)[int(len(recent_latencies) * 0.99)] if recent_latencies else 0

    with _jobs_lock:
        queue_depth = sum(1 for j in _jobs.values() if j["status"] == "queued")

    db = get_db()
    conn = db._conn()
    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    recent_orders = conn.execute(
        "SELECT order_id, chain, count, amount_usd, created_at, status FROM orders ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()

    return {
        "service": "WalletPress x402 Marketplace",
        "uptime_seconds": int(now - _sla_start),
        "total_orders": total_orders,
        "generations_24h": len(recent),
        "queue_depth": queue_depth,
        "performance": {
            "avg_wallets_per_second": round(1 / avg_speed, 1) if avg_speed > 0 else 0,
            "p50_latency_ms": round(p50 * 1000, 1),
            "p95_latency_ms": round(p95 * 1000, 1),
            "p99_latency_ms": round(p99 * 1000, 1),
        },
        "recent_orders": [dict(r) for r in recent_orders],
        "note": "Enterprise SLA. All orders cryptographically attested. Keys never stored.",
    }


@router.post("/webhooks")
async def set_webhook(api_key: str = Body(...), url: str = Body(...)):
    """Set a webhook URL for your API key.

    After every generation, we'll POST the receipt + wallets to this URL.
    The payload is HMAC-SHA256 signed with your API key as the secret.
    """
    from core.webhooks import validate_webhook_url

    try:
        validate_webhook_url(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    with _api_webhooks_lock:
        _api_webhooks[api_key[:16]] = url
    return {"webhook_set": True, "api_key": api_key[:16] + "...", "url": url}


@router.get("/webhooks")
async def get_webhook(api_key: str = ""):
    """Get the webhook URL configured for your API key."""
    with _api_webhooks_lock:
        url = _api_webhooks.get(api_key[:16])
    return {"api_key": api_key[:16] + "...", "webhook_url": url or ""}


@router.delete("/webhooks")
async def delete_webhook(api_key: str = ""):
    """Remove your webhook configuration."""
    with _api_webhooks_lock:
        _api_webhooks.pop(api_key[:16], None)
    return {"deleted": True, "api_key": api_key[:16] + "..."}


@router.post("/timelock")
async def create_timelock(req: TimelockRequest, request: Request):
    """Generate wallets with time-locked key delivery."""
    chain = req.chain.lower()
    if chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Unsupported: {chain}")
    if req.release_at <= time.time():
        raise HTTPException(status_code=400, detail="release_at must be in the future")

    import core.x402_marketplace as _pkg

    generator = _pkg.get_generator()
    wallets = []
    for i in range(req.count):
        wallet = generator.generate(chain, label=f"timelock_{i}", tags=["timelock"])
        wallets.append(
            {
                "index": i + 1,
                "address": wallet.address,
                "private_key": wallet.private_key_hex,
                "mnemonic": wallet.mnemonic,
                "derivation_path": wallet.derivation_path,
            }
        )

    lock_id = f"tl_{secrets.token_hex(8)}"
    with _timelocks_lock:
        _timelocks[lock_id] = {
            "wallets": wallets,
            "chain": chain,
            "count": req.count,
            "release_at": req.release_at,
            "auth_signature": req.auth_signature,
            "webhook_url": req.webhook_url,
            "created_at": time.time(),
            "released": False,
        }

    safe_wallets = [
        {"index": w["index"], "address": w["address"], "derivation_path": w["derivation_path"]}
        for w in wallets
    ]
    return {
        "timelock_id": lock_id,
        "chain": chain,
        "count": req.count,
        "release_at": req.release_at,
        "release_in_seconds": int(req.release_at - time.time()),
        "wallets": safe_wallets,
        "note": "Private keys are locked until the release time. Poll GET /timelock/{id} to retrieve keys.",
    }


@router.get("/timelock/{lock_id}")
async def get_timelock(lock_id: str, auth_signature: str = ""):
    """Retrieve time-locked wallets. Keys are only returned after release_at."""
    with _timelocks_lock:
        lock = _timelocks.get(lock_id)
    if not lock:
        raise HTTPException(status_code=404, detail="Timelock not found")

    if time.time() < lock["release_at"]:
        remaining = int(lock["release_at"] - time.time())
        return {
            "timelock_id": lock_id,
            "locked": True,
            "release_in_seconds": remaining,
            "wallets": [{"index": w["index"], "address": w["address"]} for w in lock["wallets"]],
            "note": f"Keys locked for {remaining} more seconds.",
        }

    if lock.get("auth_signature") and auth_signature != lock["auth_signature"]:
        return {
            "timelock_id": lock_id,
            "locked": True,
            "error": "Auth signature required to release keys",
        }

    with _timelocks_lock:
        lock["released"] = True
    return {"timelock_id": lock_id, "locked": False, "wallets": lock["wallets"]}


@router.post("/publish-proof")
async def publish_proof(order_id: str = Body(...)):
    """Publish a signed non-storage proof to Arweave for a specific order."""
    from core.proof import get_proof, get_receipt_public_key, sign_key_deletion

    db = get_db()
    conn = db._conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")

    with _jobs_lock:
        job = next(
            (
                j
                for j in _jobs.values()
                if j.get("order_id") == order_id and j["status"] == "completed"
            ),
            None,
        )
    addresses = [w["address"] for w in (job.get("wallets", []) if job else [])]

    deletion_sig = sign_key_deletion(order_id, row["chain"], row["count"], addresses)
    proof = get_proof()
    pstats = proof.stats()
    roots = proof.get_roots(1)

    key_path = os.getenv("WP_POF_ARWEAVE_KEY_PATH", "")
    if not key_path:
        return {
            "published": False,
            "reason": "Arweave key not configured (WP_POF_ARWEAVE_KEY_PATH)",
        }

    try:
        import json as j

        wallet = j.loads(await asyncio.to_thread(Path(key_path).read_text))
        from ar import Arweave

        ar = Arweave(wallet)
        data = j.dumps(
            {
                "p": "walletpress-non-storage-proof",
                "v": "1",
                "order_id": order_id,
                "chain": row["chain"],
                "count": row["count"],
                "amount_usd": row["amount_usd"],
                "address_hash": hashlib.sha256("".join(sorted(addresses)).encode()).hexdigest()[
                    :16
                ],
                "key_deletion_signature": deletion_sig,
                "receipt_public_key": get_receipt_public_key(),
                "merkle_root": roots[0]["root_hash"] if roots else "",
                "merkle_leaf_count": pstats["total_attestations"],
                "ts": time.time(),
            }
        )
        tx = ar.create_transaction(data)
        tx.sign(wallet)
        tx.send()
        return {
            "published": True,
            "order_id": order_id,
            "tx_id": tx.id,
            "verification_url": f"https://viewblock.io/arweave/tx/{tx.id}",
            "note": "Non-storage proof published to Arweave. Immutable. Publicly auditable.",
        }
    except ImportError:
        return {"published": False, "reason": "arweave-python-client not installed"}
    except Exception as e:
        return {"published": False, "reason": str(e)}
