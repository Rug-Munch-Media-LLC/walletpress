"""Tests: Proof of Generation system."""

import os
import tempfile
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-proof-unit"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_proof_")

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from core.proof import (
    PROOF_VERSION,
    ProofOfGeneration,
    anchor_source_commit,
    get_receipt_public_key,
    get_source_tree_hash,
    sign_key_deletion,
    sign_receipt,
    verify_receipt,
)


def _proof() -> ProofOfGeneration:
    tmp = Path(tempfile.mkstemp(suffix=".db")[1])
    return ProofOfGeneration(tmp)


def test_proof_version():
    assert isinstance(PROOF_VERSION, str)
    assert len(PROOF_VERSION) > 0


def test_attest():
    p = _proof()
    p.attest("test_wallet_1", "eth", "0xabc", "0xpubkey")
    att = p.get_attestation("test_wallet_1")
    assert att is not None
    assert att["address"] == "0xabc"
    assert att["wallet_id"] == "test_wallet_1"
    assert att["chain"] == "eth"


def test_get_attestation_missing():
    p = _proof()
    assert p.get_attestation("nonexistent") is None


def test_compute_merkle_root():
    p = _proof()
    p.attest("w1", "eth", "0x1", "pk1")
    p.attest("w2", "sol", "0x2", "pk2")
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
    p.attest("w1", "eth", "0x1", "pk1")
    root_hash, _ = p.compute_merkle_root()
    result = p.commit(root_hash, 1)
    assert isinstance(result, dict)
    assert "root_hash" in result or result.get("committed_at") is not None


def test_get_roots():
    p = _proof()
    assert p.get_roots() == []
    p.attest("w1", "eth", "0x1", "pk1")
    rh, lc = p.compute_merkle_root()
    p.commit(rh, lc)
    roots = p.get_roots()
    assert len(roots) >= 1


def test_verify():
    p = _proof()
    p.attest("w1", "eth", "0xabc", "pk")
    result = p.verify("w1", "0xabc", "pk")
    assert isinstance(result, dict)
    assert "verified" in result or "valid" in result


def test_stats():
    p = _proof()
    p.attest("w1", "eth", "0x1", "pk1")
    stats = p.stats()
    assert stats["total_attestations"] >= 1


def test_get_proof_path():
    p = _proof()
    leaf1 = p.attest("w1", "eth", "0x1", "pk1")
    p.attest("w2", "sol", "0x2", "pk2")
    rh, _ = p.compute_merkle_root()
    p.commit(rh, 2)
    path = p.get_proof_path(leaf1)
    assert isinstance(path, list)
    # After compute_merkle_root + commit, proof paths should exist
    if len(path) > 0:
        assert "sibling_hash" in path[0]


def test_get_proof_path_by_leaf():
    p = _proof()
    leaf = p.attest("wallet_x", "eth", "0xaddr", "pk")
    path = p.get_proof_path(leaf)
    assert isinstance(path, list)


def test_sign_receipt():
    sig = sign_receipt("order-123", "eth", 5, 99.99, 1234567890.0)
    assert isinstance(sig, str)
    assert len(sig) > 0


def test_verify_receipt():
    order_id = "order-verify-1"
    sig = sign_receipt(order_id, "eth", 3, 50.0, 2000000.0)
    pubkey = get_receipt_public_key()
    assert len(pubkey) > 0
    result = verify_receipt(order_id, "eth", 3, 50.0, 2000000.0, sig, pubkey)
    assert result is True


def test_verify_receipt_wrong_key():
    sig = sign_receipt("order-bad", "eth", 1, 10.0, 3000000.0)
    result = verify_receipt("order-bad", "eth", 1, 10.0, 3000000.0, sig, "00" * 32)
    assert result is False


def test_verify_receipt_wrong_data():
    sig = sign_receipt("order-ok", "eth", 2, 20.0, 4000000.0)
    pubkey = get_receipt_public_key()
    result = verify_receipt("order-wrong", "eth", 2, 20.0, 4000000.0, sig, pubkey)
    assert result is False


def test_get_receipt_public_key():
    key = get_receipt_public_key()
    assert isinstance(key, str)
    assert len(key) > 0
    # Should be hex (ed25519 public key is 32 bytes = 64 hex chars)
    assert len(key) == 64 or len(key) == 128


def test_sign_key_deletion():
    sig = sign_key_deletion("order-del-1", "eth", 3, ["0xaddr1", "0xaddr2"])
    assert isinstance(sig, str)
    assert len(sig) > 0


def test_get_source_tree_hash():
    # Should return a hash or "unknown" (depends on git availability)
    result = get_source_tree_hash()
    assert isinstance(result, str)
    assert len(result) > 0


def test_anchor_source_commit_no_arweave_key():
    result = anchor_source_commit()
    assert isinstance(result, dict)
    # Without WP_POF_ARWEAVE_KEY_PATH, it should fail gracefully
    assert result.get("anchored") is False


def test_verify_merkle_proof_single_leaf():
    p = _proof()
    leaf = p.attest("single", "eth", "0xaddr", "pk")
    rh, _ = p.compute_merkle_root()
    # Single leaf: leaf IS the root
    assert p.verify_merkle_proof(leaf, rh) is True


def test_verify_merkle_proof_valid():
    p = _proof()
    leaf1 = p.attest("v1", "eth", "0xa1", "pk1")
    p.attest("v2", "sol", "0xa2", "pk2")
    rh, _ = p.compute_merkle_root()
    assert p.verify_merkle_proof(leaf1, rh) is True


def test_verify_merkle_proof_invalid():
    p = _proof()
    leaf = p.attest("bad", "eth", "0xaddr", "pk")
    p.compute_merkle_root()
    assert p.verify_merkle_proof(leaf, "00" * 32) is False


def test_get_attestation_by_leaf():
    p = _proof()
    leaf = p.attest("by_leaf", "eth", "0xaddr", "pk")
    att = p.get_attestation_by_leaf(leaf)
    assert att is not None
    assert att["wallet_id"] == "by_leaf"


def test_get_attestation_by_leaf_missing():
    p = _proof()
    att = p.get_attestation_by_leaf("nonexistenthash")
    assert att is None


def test_get_proof_by_wallet_exists():
    p = _proof()
    p.attest("gpw1", "eth", "0xaddr", "pk")
    result = p.get_proof_by_wallet("gpw1")
    assert result["exists"] is True
    assert result["wallet_id"] == "gpw1"


def test_get_proof_by_wallet_missing():
    p = _proof()
    result = p.get_proof_by_wallet("nonexistent")
    assert result["exists"] is False
    assert "error" in result


def test_verify_nonexistent_wallet():
    p = _proof()
    result = p.verify("ghost", "0xaddr", "pk")
    assert result["verified"] is False
    assert "No attestation found" in result["reason"]


def test_verify_without_public_key():
    p = _proof()
    p.attest("nokey", "eth", "0xaddr", "pk1")
    result = p.verify("nokey", "0xaddr")
    assert result["verified"] is True


def test_attest_different_wallets_different_leaves():
    p = _proof()
    leaf1 = p.attest("dup1", "eth", "0xa", "pk1")
    leaf2 = p.attest("dup2", "eth", "0xb", "pk2")
    assert leaf1 != leaf2


def test_compute_merkle_root_odd_leaves():
    p = _proof()
    p.attest("odd1", "eth", "0xa", "pk1")
    p.attest("odd2", "sol", "0xb", "pk2")
    p.attest("odd3", "bsc", "0xc", "pk3")
    rh, count = p.compute_merkle_root()
    assert rh is not None
    assert len(rh) > 0
    assert count == 3


def test_commit_to_root_info():
    p = _proof()
    p.attest("commit_info", "eth", "0xa", "pk")
    rh, count = p.compute_merkle_root()
    p.commit(rh, count)
    result = p.get_proof_by_wallet("commit_info")
    assert result["exists"] is True
    assert "root" in result
    assert result["committed"] is True


def test_get_proof_by_wallet_with_full_merkle():
    p = _proof()
    p.attest("full1", "eth", "0xa1", "pk1")
    p.attest("full2", "sol", "0xa2", "pk2")
    rh, count = p.compute_merkle_root()
    p.commit(rh, count)
    result = p.get_proof_by_wallet("full1")
    assert result["exists"] is True
    assert result["merkle_proof_verified"] is True
