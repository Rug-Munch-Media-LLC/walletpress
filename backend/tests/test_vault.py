"""Tests: vault storage, encryption, and schema migration."""
import os
import tempfile
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-vault-password"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_vault_")

from core.config import cfg
cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from core.vault import Vault, WalletEntry


def _vault() -> Vault:
    tmp = Path(tempfile.mkstemp(suffix=".db")[1])
    v = Vault(tmp)
    return v


def test_put_and_get():
    v = _vault()
    e = WalletEntry(id="test1", chain="eth", address="0xabc", label="test", tags=[], group="", created_at=100.0)
    assert v.put(e)
    got = v.get("test1")
    assert got is not None
    assert got.id == "test1"
    assert got.chain == "eth"
    assert got.address == "0xabc"


def test_get_missing():
    v = _vault()
    assert v.get("nonexistent") is None


def test_delete():
    v = _vault()
    v.put(WalletEntry(id="del1", chain="sol", address="abc", label="", tags=[], group="", created_at=1.0))
    assert v.delete("del1")
    assert v.get("del1") is None


def test_count():
    v = _vault()
    assert v.count() == 0
    v.put(WalletEntry(id="c1", chain="eth", address="0x1", label="", tags=[], group="", created_at=1.0))
    v.put(WalletEntry(id="c2", chain="sol", address="abc", label="", tags=[], group="", created_at=2.0))
    assert v.count() == 2
    assert v.count(chain="eth") == 1


def test_list():
    v = _vault()
    v.put(WalletEntry(id="l1", chain="btc", address="1abc", label="", tags=[], group="", created_at=3.0))
    v.put(WalletEntry(id="l2", chain="btc", address="1def", label="", tags=[], group="", created_at=1.0))
    wallets = v.list(chain="btc")
    assert len(wallets) == 2


def test_rotation():
    v = _vault()
    v.put(WalletEntry(id="r1", chain="eth", address="0xold", label="", tags=[], group="", created_at=1.0))
    v.record_rotation("r1", "0xnew", reason="test")
    rots = v.get_rotations("r1")
    assert len(rots) == 1
    assert rots[0]["new_address"] == "0xnew"


def test_search_by_address():
    v = _vault()
    v.put(WalletEntry(id="s1", chain="eth", address="0xdeadbeef", label="vip", tags=[], group="", created_at=1.0))
    v.put(WalletEntry(id="s2", chain="sol", address="0xdeadbeef", label="vip2", tags=[], group="", created_at=1.0))
    results = v.search("eth")
    assert len(results) >= 1, f"Expected at least 1 result, got {len(results)}"


def test_search_by_label():
    v = _vault()
    v.put(WalletEntry(id="s2", chain="sol", address="abc123", label="my-trading-wallet", tags=[], group="", created_at=1.0))
    results = v.search("trading")
    assert len(results) >= 1, f"Expected at least 1 result, got {len(results)}"


def test_schema_version():
    v = _vault()
    conn = v._new_conn()
    row = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()
    conn.close()
    assert row and row[0] == Vault.SCHEMA_VERSION


def test_encrypt_decrypt():
    v = _vault()
    encrypted = v.encrypt_key("my-secret-key")
    assert encrypted != "my-secret-key"
    decrypted = v.decrypt_key(encrypted)
    assert decrypted == "my-secret-key"


def test_vault_requires_password():
    passwd = os.environ.pop("WP_VAULT_PASSWORD", None)
    tmp = Path(tempfile.mkstemp(suffix=".db")[1])
    try:
        cfg.clear_vault_password()
        raised = False
        try:
            Vault(tmp)
        except RuntimeError:
            raised = True
        assert raised, "Vault should raise RuntimeError without password"
    finally:
        if passwd:
            os.environ["WP_VAULT_PASSWORD"] = passwd
            cfg._vault_password = passwd


def test_stats():
    v = _vault()
    v.put(WalletEntry(id="st1", chain="eth", address="0x1", label="", tags=[], group="", created_at=1.0))
    v.put(WalletEntry(id="st2", chain="sol", address="abc", label="", tags=[], group="", created_at=2.0))
    v.put(WalletEntry(id="st3", chain="eth", address="0x2", label="", tags=[], group="", created_at=3.0))
    stats = v.stats()
    assert stats["total_wallets"] == 3
    assert stats["chains_used"] == 2
    assert stats["by_chain"]["eth"] == 2
    assert stats["by_chain"]["sol"] == 1
