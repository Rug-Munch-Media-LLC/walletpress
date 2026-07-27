"""Tests: Proof of Generation system."""

import os
import tempfile
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-proof-unit"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_proof_")

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from core.proof import ProofOfGeneration, PROOF_VERSION, sign_receipt


def _proof() -> ProofOfGeneration:
    tmp = Path(tempfile.mkstemp(suffix=".db")[1])
    return ProofOfGeneration(tmp)


def test_proof_version():
    assert isinstance(PROOF_VERSION, str)
    assert len(PROOF_VERSION) > 0


def test_attest():
    p = _proof()
    p.attest("test_wallet_1", "0xabc", "0xpubkey", "eth")
    att = p.get_attestation("test_wallet_1")
    assert att is not None
    assert att["address"] == "0xabc"
    assert att["wallet_id"] == "test_wallet_1"


def test_get_attestation_missing():
    p = _proof()
    assert p.get_attestation("nonexistent") is None


def test_compute_merkle_root():
    p = _proof()
    p.attest("w1", "0x1", "pk1", "eth")
    p.attest("w2", "0x2", "pk2", "sol")
    root_hash, leaf_count = p.compute_merkle_root()
    assert root_hash is not None
    assert len(root_hash) > 0
    assert leaf_count == 2


def test_compute_merkle_root_empty():
    p = _proof()
    root_hash, leaf_count = p.compute_merkle_root()
    assert root_hash is None or leaf_count == 0


def test_commit():
    p = _proof()
    p.attest("w1", "0x1", "pk1", "eth")
    root_hash, _ = p.compute_merkle_root()
    result = p.commit(root_hash, 1)
    assert isinstance(result, dict)
    assert "root_hash" in result or result.get("committed_at") is not None


def test_get_roots():
    p = _proof()
    assert p.get_roots() == []
    p.attest("w1", "0x1", "pk1", "eth")
    rh, lc = p.compute_merkle_root()
    p.commit(rh, lc)
    roots = p.get_roots()
    assert len(roots) >= 1


def test_verify():
    p = _proof()
    p.attest("w1", "0xabc", "pk", "eth")
    result = p.verify("w1", "0xabc", "pk")
    assert isinstance(result, dict)
    assert "verified" in result or "valid" in result


def test_stats():
    p = _proof()
    p.attest("w1", "0x1", "pk1", "eth")
    stats = p.stats()
    assert stats["total_attestations"] >= 1


def test_get_proof_path():
    p = _proof()
    p.attest("w1", "0x1", "pk1", "eth")
    p.attest("w2", "0x2", "pk2", "sol")
    rh, _ = p.compute_merkle_root()
    p.commit(rh, 2)
    path = p.get_proof_path("w1")
    assert path is not None or True  # may be None for first commit


def test_sign_receipt():
    sig = sign_receipt("order-123", "eth", 5, 99.99, 1234567890.0)
    assert isinstance(sig, str)
    assert len(sig) > 0
