"""Proof of Generation Digest — periodic Merkle root publishing.

Every N attestations, compute the Merkle root and record it.
This digest serves as the immutable record of all wallet generations.

The Merkle root can be:
  1. Stored locally in SQLite (always, free)
  2. Published to the /api/v1/proof/roots endpoint (always)
  3. Sealed on Arweave for permanent immutable storage (planned)
  4. Committed to Ethereum as calldata for on-chain timestamp (planned)

ARCHITECTURE:
    Attestations (leaves)
        │
        ▼
    Merkle Tree (batches of 100-1000 attestations)
        │
        ▼
    Merkle Root (hash of all leaves in batch)
        │
        ├──→ SQLite (always)
        ├──→ API endpoint (always)
        ├──→ Arweave (planned)
        └──→ Ethereum (planned)
"""

from __future__ import annotations

import time
from pathlib import Path

from .proof import PROOF_VERSION, get_proof


def create_digest() -> dict:
    """Create a Proof of Generation digest from all pending attestations.

    Computes the Merkle root, commits it, and returns a digest document
    that can be published as proof of all wallet generations up to now.

    Returns:
        Dict with root_hash, leaf_count, timestamp, and attestation IDs.
    """
    proof = get_proof()
    root_hash, leaf_count = proof.compute_merkle_root()

    if not root_hash or leaf_count == 0:
        return {"committed": False, "leaf_count": 0}

    result = proof.commit(root_hash, leaf_count)

    return {
        "committed": True,
        "version": PROOF_VERSION,
        "root_hash": root_hash,
        "leaf_count": leaf_count,
        "timestamp": time.time(),
        "verification_url": f"/api/v1/proof/root/{root_hash}",
        "commitment": result,
    }


def verify_wallet(wallet_id: str, address: str, public_key_hex: str = "") -> dict:
    """Verify a specific wallet's attestation.

    Returns the full provenance including the Merkle path.
    """
    proof = get_proof()
    return proof.verify(wallet_id, address, public_key_hex)


def generate_verification_page(root_hash: str, output_path: Path | None = None) -> str:
    """Generate an HTML verification page for a Merkle root.

    This page can be statically hosted or published as proof.
    Anyone visiting this URL can verify any wallet under this root.
    """
    proof = get_proof()
    roots = proof.get_roots(1)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>WalletPress Proof of Generation — Root Verification</title>
<style>
body {{ font-family: monospace; background: #f5f5f5; padding: 40px; }}
.container {{ max-width: 640px; margin: 0 auto; background: #fff; padding: 32px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
h1 {{ font-size: 20px; margin-bottom: 16px; }}
.meta {{ font-size: 13px; color: #666; margin-bottom: 24px; }}
.hash {{ font-family: monospace; background: #f0f0f0; padding: 12px; border-radius: 4px; word-break: break-all; font-size: 12px; }}
.verified {{ color: #10b981; font-weight: 600; }}
</style>
</head>
<body>
<div class="container">
<h1>WalletPress Proof of Generation</h1>
<div class="meta">
<strong>Merkle Root:</strong>
<div class="hash">{root_hash}</div>
</div>
<div class="meta">
<strong>Version:</strong> {PROOF_VERSION}<br>
<strong>Timestamp:</strong> {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}<br>
<strong>Total Wallet Attestations:</strong> {roots[0]['leaf_count'] if roots else 'N/A'}<br>
</div>
<p>This Merkle root is the cryptographic commitment for all wallet
generations in this batch. Each wallet's attestation is a leaf in
this Merkle tree.</p>
<p>To verify a specific wallet, visit:<br>
<code>/api/v1/proof/verify/{{wallet_id}}</code></p>
<p class="verified">This attestation is immutable and timestamped.</p>
</div>
</body>
</html>"""

    if output_path:
        output_path.write_text(html)

    return html
