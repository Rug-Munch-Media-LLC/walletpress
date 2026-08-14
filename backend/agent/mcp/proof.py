"""Proof-of-generation & x402 marketplace tools for the WalletPress AI Agent.

Attestation statistics, Merkle root commits, wallet provenance/verification,
and the x402 order verification / transparency endpoints.
"""

from __future__ import annotations

from agent.mcp.instance import mcp

# ── PROOF OF GENERATION ────────────────────────────────────


@mcp.tool()
def proof_attestations() -> dict:
    """Get Proof of Generation statistics — total attestations, committed, uncommitted roots."""
    from core.proof import get_proof

    return get_proof().stats()


@mcp.tool()
def proof_commit_pending(chain: str = "local") -> dict:
    """Commit all pending attestations to a Merkle root.

    Args:
        chain: 'local' (SQLite, free), 'arweave' (permanent, ~$0.000001),
               'ethereum' (on-chain, ~$5-50 gas)
    """
    from core.proof import get_proof

    proof = get_proof()
    root_hash, count = proof.compute_merkle_root()
    if not root_hash:
        return {"committed": False, "reason": "No pending attestations"}
    result = proof.commit(root_hash, count, commitment_chain=chain)
    return {
        "committed": True,
        "root_hash": root_hash,
        "attestation_count": count,
        "chain": chain,
        "commitment_tx": result.get("commitment_tx", ""),
        "verification_url": result.get("verification_url", ""),
    }


@mcp.tool()
def proof_verify_wallet(wallet_id: str) -> dict:
    """Verify a wallet's Proof of Generation attestation.

    Args:
        wallet_id: Wallet ID from vault_list
    """
    from core.proof import get_proof
    from core.vault import get_vault

    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        return {"error": f"Wallet {wallet_id} not found"}
    result = get_proof().verify(wallet_id, wallet.address, wallet.public_key)
    return result


@mcp.tool()
def proof_provenance(wallet_id: str) -> dict:
    """Get the complete cryptographic provenance for a wallet.

    Includes the Merkle proof path so it can be independently verified.
    This is the wallet's birth certificate.

    Args:
        wallet_id: Wallet ID from vault_list
    """
    from core.proof import get_proof
    from core.vault import get_vault

    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        return {"error": f"Wallet {wallet_id} not found"}
    result = get_proof().get_proof_by_wallet(wallet_id)
    return result


@mcp.tool()
def proof_roots(limit: int = 10) -> dict:
    """List recent Merkle roots committed for wallet attestations.

    Args:
        limit: Max roots to return (default 10)
    """
    from core.proof import get_proof

    proof = get_proof()
    return {
        "stats": proof.stats(),
        "roots": proof.get_roots(limit),
    }


@mcp.tool()
def verify_order(order_id: str) -> dict:
    """Verify an x402 marketplace order — proves we generated the wallets and didn't keep keys.

    Returns the order details, receipt signature, and attestation proof.
    Anyone can independently verify this order was fulfilled by WalletPress.

    Args:
        order_id: Order ID from the generate response (e.g. 'x402_abc123...')
    """
    from core.config import cfg
    from core.proof import get_receipt_public_key
    from core.wallet_db_pool import DbPool

    pool = DbPool(cfg.data_dir / "marketplace.db")
    row = pool.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if not row:
        return {"error": f"Order {order_id} not found"}
    pubkey = get_receipt_public_key()
    return {
        "order_id": order_id,
        "chain": row["chain"],
        "count": row["count"],
        "amount_usd": row["amount_usd"],
        "created_at": row["created_at"],
        "status": row["status"],
        "payment_method": "onchain"
        if row.get("payment_tx") and row["payment_tx"] != "free"
        else "free",
        "receipt_public_key": pubkey,
        "verification": {
            "keys_stored": False,
            "keys_returned_once": True,
            "open_source": "https://github.com/cryptorugmuncher/walletpress",
            "note": "This order was fulfilled by WalletPress. Keys were generated in memory and returned once.",
        },
    }


@mcp.tool()
def marketplace_transparency() -> dict:
    """Get the public transparency dashboard — stats, roots, guarantees.

    Proves WalletPress is operating transparently. No secrets here.
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
