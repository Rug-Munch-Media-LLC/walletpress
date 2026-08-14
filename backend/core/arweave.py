"""Arweave Commitment — permanent, immutable storage for Proof of Generation roots.

Merkle roots of wallet attestations can be committed to the Arweave
permaweb for ~$0.000001 per write. Once written, they can NEVER be
modified or deleted.

This is the "permanent" layer of the Proof of Generation system:
  SQLite (instant) → API (always) → Arweave (permanent)

Trust: An Arweave commitment proves the Merkle root existed before
the block timestamp. No one can forge a root that was committed
after the fact.

REQUIRES: An Arweave wallet with AR tokens and the arweave-py library.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("wp.arweave")

# Try to import arweave
try:
    from arweave import Transaction, Wallet
    HAS_ARWEAVE = True
except ImportError:
    HAS_ARWEAVE = False


ARWEAVE_WALLET_PATH = os.getenv("WP_ARWEAVE_WALLET", "")


def commit_root(root_hash: str, leaf_count: int, version: str = "walletpress-proof-v1") -> dict:
    """Commit a Merkle root to the Arweave permaweb.

    Args:
        root_hash: The Merkle root hash to commit
        leaf_count: Number of attestations in this root
        version: Protocol version string

    Returns:
        Dict with transaction_id, block_height, and permanent_url.
        If Arweave is not configured, returns a command to execute.
    """
    if not HAS_ARWEAVE or not ARWEAVE_WALLET_PATH:
        return {
            "committed": False,
            "chain": "arweave",
            "note": "Arweave not configured. Set WP_ARWEAVE_WALLET env var.",
            "pending_tx": _build_unsigned_tx(root_hash, leaf_count, version),
        }

    try:
        wallet = Wallet(ARWEAVE_WALLET_PATH)
        tx = Transaction(wallet, data=json.dumps({
            "protocol": version,
            "root_hash": root_hash,
            "leaf_count": leaf_count,
            "timestamp": __import__("time").time(),
            "type": "walletpress_proof_of_generation",
        }).encode())

        tx.add_tag("Protocol", version)
        tx.add_tag("Type", "walletpress_proof_of_generation")
        tx.add_tag("RootHash", root_hash)
        tx.add_tag("LeafCount", str(leaf_count))

        tx.sign()
        tx.send()

        tx_id = tx.id
        return {
            "committed": True,
            "chain": "arweave",
            "transaction_id": tx_id,
            "permanent_url": f"https://arweave.net/{tx_id}",
            "root_hash": root_hash,
        }
    except Exception as e:
        logger.error(f"Arweave commit failed: {e}")
        return {
            "committed": False,
            "chain": "arweave",
            "error": str(e),
            "pending_tx": _build_unsigned_tx(root_hash, leaf_count, version),
        }


def _build_unsigned_tx(root_hash: str, leaf_count: int, version: str) -> dict:
    """Build an unsigned Arweave transaction for manual submission.

    Returns the transaction data that can be submitted manually
    via arweave.net/tx or the Arweave CLI.
    """
    return {
        "protocol": version,
        "type": "walletpress_proof_of_generation",
        "root_hash": root_hash,
        "leaf_count": leaf_count,
        "arweave_tags": {
            "Protocol": version,
            "Type": "walletpress_proof_of_generation",
            "RootHash": root_hash,
            "LeafCount": str(leaf_count),
        },
        "submission_url": "https://arweave.net/tx",
        "cli_command": f"arweave deploy {root_hash}.json --wallet {ARWEAVE_WALLET_PATH or '/path/to/wallet.json'}",
    }
