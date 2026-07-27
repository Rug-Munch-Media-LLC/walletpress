"""Additional unit tests: vault operations beyond the base test_vault.py."""

import os
import tempfile
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-vault-password-unit"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_vault_unit_")

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

import time
from core.vault import Vault, WalletEntry


def _vault() -> Vault:
    tmp = Path(tempfile.mkstemp(suffix=".db")[1])
    return Vault(tmp)


def _entry(id: str, chain: str = "eth", address: str = "0xabc", label: str = "") -> WalletEntry:
    return WalletEntry(
        id=id, chain=chain, address=address, label=label, tags=[], group="", created_at=time.time()
    )


def test_put_twice_updates():
    v = _vault()
    e1 = _entry("dup", "eth", "0xold")
    e2 = _entry("dup", "sol", "0xnew")
    assert v.put(e1)
    assert v.put(e2)
    got = v.get("dup")
    assert got is not None
    assert got.chain == "sol"
    assert got.address == "0xnew"


def test_list_empty():
    v = _vault()
    wallets = v.list(chain="nonexistent_chain_xyz")
    assert len(wallets) == 0


def test_list_all():
    v = _vault()
    v.put(_entry("a1", "eth"))
    v.put(_entry("a2", "sol"))
    v.put(_entry("a3", "btc"))
    wallets = v.list()
    assert len(wallets) == 3


def test_list_pagination():
    v = _vault()
    for i in range(10):
        v.put(_entry(f"p{i}", "eth", f"0x{i:040x}"))
    page1 = v.list(limit=3, offset=0)
    assert len(page1) == 3
    page2 = v.list(limit=3, offset=3)
    assert len(page2) == 3
    # Ensure pages are different
    ids1 = {w.id for w in page1}
    ids2 = {w.id for w in page2}
    assert ids1.isdisjoint(ids2)


def test_get_by_address():
    v = _vault()
    v.put(_entry("byaddr1", "eth", "0xdeadbeef"))
    got = v.get_by_address("0xdeadbeef")
    assert got is not None
    assert got.id == "byaddr1"


def test_get_by_address_missing():
    v = _vault()
    assert v.get_by_address("0xnonexistent") is None


def test_get_by_address_empty_string():
    v = _vault()
    assert v.get_by_address("") is None


def test_record_rotation_multiple():
    v = _vault()
    v.put(_entry("rot", "eth", "0xoriginal"))
    v.record_rotation("rot", "0xaddr1", reason="security")
    v.record_rotation("rot", "0xaddr2", reason="compromised")
    v.record_rotation("rot", "0xaddr3", reason="rotation")
    rots = v.get_rotations("rot")
    assert len(rots) == 3
    assert rots[0]["new_address"] == "0xaddr3"
    assert rots[2]["new_address"] == "0xaddr1"


def test_rotation_no_wallet():
    """Rotation should work even if wallet doesn't exist (orphan rotation)."""
    v = _vault()
    v.record_rotation("orphan", "0xnew", reason="test")
    rots = v.get_rotations("orphan")
    assert len(rots) == 1


def test_stats_empty():
    v = _vault()
    stats = v.stats()
    assert stats["total_wallets"] == 0
    assert stats["chains_used"] == 0
    assert stats["encrypted_wallets"] == 0
    assert stats["rotations"] == 0


def test_stats_after_delete():
    v = _vault()
    v.put(_entry("s1", "eth", "0x1"))
    v.put(_entry("s2", "sol", "abc"))
    v.put(_entry("s3", "eth", "0x2"))
    assert v.stats()["total_wallets"] == 3
    v.delete("s1")
    assert v.stats()["total_wallets"] == 2
    assert v.stats()["by_chain"]["eth"] == 1


def test_delete_non_existent():
    v = _vault()
    result = v.delete("nonexistent_id_xyz")
    assert result is False


def test_delete_then_re_add():
    v = _vault()
    v.put(_entry("re", "eth", "0xoriginal"))
    v.delete("re")
    assert v.get("re") is None
    v.put(_entry("re", "sol", "0xnew"))
    got = v.get("re")
    assert got is not None
    assert got.chain == "sol"


def test_search_fts_fallback():
    """Search should work even if FTS table is not available."""
    v = _vault()
    e = _entry("fts1", "eth", "0x1234abc", label="my-test-wallet")
    v.put(e)
    results = v.search("my-test-wallet")
    assert len(results) >= 1
    assert results[0].id == "fts1"


def test_search_by_chain():
    v = _vault()
    v.put(_entry("sch1", "eth", "0xaaa"))
    v.put(_entry("sch2", "sol", "bbb"))
    results = v.search("eth")
    assert len(results) >= 1


def test_encrypt_decrypt_roundtrip():
    v = _vault()
    secrets = ["my-secret-key", "abc123", "0xdeadbeefcafebabe", ""]
    for secret in secrets:
        encrypted = v.encrypt_key(secret)
        assert encrypted != secret
        decrypted = v.decrypt_key(encrypted)
        assert decrypted == secret


def test_encrypt_different_each_time():
    v = _vault()
    e1 = v.encrypt_key("same-secret")
    e2 = v.encrypt_key("same-secret")
    assert e1 != e2  # should have different salts/nonces


def test_vault_with_encrypted_flag():
    v = _vault()
    e = WalletEntry(
        id="enc",
        chain="eth",
        address="0xencrypted",
        label="",
        tags=[],
        group="",
        created_at=1.0,
        encrypted_key="encrypted_blob",
        encrypted=True,
    )
    v.put(e)
    got = v.get("enc")
    assert got is not None
    assert got.encrypted is True
    assert got.encrypted_key == "encrypted_blob"


def test_vault_with_tags():
    v = _vault()
    tags = ["hot", "trading", "defi"]
    e = WalletEntry(
        id="tags1", chain="eth", address="0x1", label="", tags=tags, group="", created_at=1.0
    )
    v.put(e)
    got = v.get("tags1")
    assert got is not None
    assert got.tags == tags


def test_vault_with_group():
    v = _vault()
    e = WalletEntry(
        id="grp1",
        chain="eth",
        address="0x1",
        label="",
        tags=[],
        group="trading-bot",
        created_at=1.0,
    )
    v.put(e)
    got = v.get("grp1")
    assert got is not None
    assert got.group == "trading-bot"


def test_vault_empty_list_returns_empty():
    v = _vault()
    wallets = v.list()
    assert wallets == []


def test_vault_count_empty():
    v = _vault()
    assert v.count() == 0


def test_vault_count_chain():
    v = _vault()
    v.put(_entry("c1", "eth"))
    v.put(_entry("c2", "eth"))
    v.put(_entry("c3", "sol"))
    assert v.count(chain="eth") == 2
    assert v.count(chain="sol") == 1
    assert v.count(chain="btc") == 0
