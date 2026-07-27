"""Unit tests: KeyStore and API key authentication (no HTTP)."""

import os
import json
import tempfile
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-vault-password-auth"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_auth_")

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from core.auth import KeyStore, role_has_at_least, ROLE_HIERARCHY


def test_create_key():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    key_id, raw_key = ks.create(label="test-key", scopes=["wallet.read"])
    assert key_id.startswith("wp_")
    assert raw_key.startswith("wp_")
    assert len(key_id) > 8
    assert len(raw_key) > 8


def test_verify_valid_key():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    _, raw_key = ks.create(label="verify-me", scopes=["wallet.read"])
    result = ks.verify(raw_key)
    assert result is not None
    assert result.label == "verify-me"
    assert "wallet.read" in result.scopes


def test_verify_wrong_key():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    ks.create(label="a", scopes=["wallet.read"])
    result = ks.verify("wp_wrong_key_that_does_not_exist")
    assert result is None


def test_verify_revoked_key():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    key_id, raw_key = ks.create(label="revoke-me", scopes=["wallet.read"])
    assert ks.verify(raw_key) is not None
    ks.revoke(key_id)
    assert ks.verify(raw_key) is None


def test_revoke_key():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    key_id, _ = ks.create(label="revocable", scopes=["wallet.read"])
    assert ks.revoke(key_id) is True
    assert ks.revoke("nonexistent") is False


def test_list_keys():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    ks.create(label="key-a", scopes=["wallet.read"])
    ks.create(label="key-b", scopes=["wallet.write", "wallet.read"])
    keys = ks.list()
    assert len(keys) == 2
    labels = {k["label"] for k in keys}
    assert labels == {"key-a", "key-b"}
    for k in keys:
        assert "id" in k
        assert "scopes" in k
        assert "created_at" in k
        assert "revoked" in k


def test_role_hierarchy():
    assert ROLE_HIERARCHY["admin"] == 3
    assert ROLE_HIERARCHY["operator"] == 2
    assert ROLE_HIERARCHY["viewer"] == 1


def test_role_has_at_least():
    assert role_has_at_least("admin", "admin") is True
    assert role_has_at_least("admin", "viewer") is True
    assert role_has_at_least("operator", "admin") is False
    assert role_has_at_least("viewer", "admin") is False
    assert role_has_at_least("viewer", "viewer") is True
    assert role_has_at_least("unknown", "viewer") is False


def test_check_scope():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    _, raw_key = ks.create(label="scoped", scopes=["wallet.read"])
    assert ks.check_scope(raw_key, "wallet.read") is True
    assert ks.check_scope(raw_key, "wallet.write") is False
    assert ks.check_scope(raw_key, "admin") is False


def test_check_scope_admin():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    _, raw_key = ks.create(label="admin-key", scopes=["admin"])
    assert ks.check_scope(raw_key, "wallet.read") is True
    assert ks.check_scope(raw_key, "wallet.write") is True
    assert ks.check_scope(raw_key, "admin") is True


def test_has_role():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    _, raw_key = ks.create(label="role-test", scopes=["wallet.read"], role="admin")
    assert ks.has_role(raw_key, "admin") is True
    assert ks.has_role(raw_key, "viewer") is True
    # operator key cannot pass admin check
    _, op_key = ks.create(label="operator-key", scopes=["wallet.read"], role="operator")
    assert ks.has_role(op_key, "admin") is False
    assert ks.has_role(op_key, "operator") is True


def test_create_invalid_role():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    import pytest

    with pytest.raises(ValueError):
        ks.create(label="bad-role", scopes=["wallet.read"], role="superadmin")


def test_persistence():
    path = Path(tempfile.mkstemp(suffix=".json")[1])
    ks1 = KeyStore(path)
    key_id, raw_key = ks1.create(label="persist-test", scopes=["wallet.read"])
    # Create new instance with same path — should load keys
    ks2 = KeyStore(path)
    assert ks2.verify(raw_key) is not None
    assert ks2.verify("wrong_key") is None


def test_flush_last_used():
    path = Path(tempfile.mkstemp(suffix=".json")[1])
    ks = KeyStore(path)
    _, raw_key = ks.create(label="flush-test", scopes=["wallet.read"])
    ks.verify(raw_key)  # this updates last_used_at in memory
    ks.flush_last_used()  # persist
    ks2 = KeyStore(path)
    key = ks2.verify(raw_key)
    assert key is not None
    assert key.last_used_at is not None, "last_used_at should be persisted after flush"


def test_get_role():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    _, raw_key = ks.create(label="role-get", scopes=["wallet.read"], role="operator")
    assert ks.get_role(raw_key) == "operator"
    assert ks.get_role("wrong_key") is None


def test_create_with_owner():
    ks = KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))
    key_id, raw_key = ks.create(
        label="owned", scopes=["wallet.read"], role="viewer", owner="user@example.com"
    )
    key = ks.verify(raw_key)
    assert key is not None
    assert key.owner == "user@example.com"
    assert key.role == "viewer"
