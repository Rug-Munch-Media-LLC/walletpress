"""Tests: wallet creation, balance check, and transaction history.

Covers the core wallet engine (WalletGenerator) and the encrypted vault
(Vault) that persists wallets and records rotation/transaction history.

Pattern follows rugcharts/backend/tests: pytest + httpx_mock for external
RPC calls, async fixtures for the FastAPI app.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-vault-password-1234567890"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_wallet_")
os.environ["WP_ADMIN_KEY"] = "test-admin-key-12345"
os.environ["WP_RATE_LIMIT"] = "0"

import pytest
from httpx import ASGITransport, AsyncClient

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from core.vault import Vault, WalletEntry
from wallet_engine.generator import WalletGenerator

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def generator() -> WalletGenerator:
    """A WalletGenerator with a vault password (keys encrypted at rest)."""
    return WalletGenerator(vault_password=cfg.vault_password)


@pytest.fixture
def vault() -> Vault:
    """A fresh on-disk Vault for each test."""
    return Vault(Path(tempfile.mkstemp(suffix=".db")[1]))


@pytest.fixture
async def client():
    """Async test client against the full FastAPI app."""
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Wallet creation ─────────────────────────────────────────────────────────


def test_generate_evm_wallet(generator):
    """Generating an EVM wallet yields a valid checksummed address."""
    wallet = generator.generate("eth", label="test-eth")
    assert wallet.chain == "eth"
    assert wallet.address.startswith("0x")
    assert len(wallet.address) == 42
    assert wallet.encrypted is True  # vault password set -> key encrypted
    assert wallet.private_key_hex  # encrypted key present
    assert wallet.label == "test-eth"


def test_generate_solana_wallet(generator):
    """Generating a Solana wallet yields a base58 address."""
    wallet = generator.generate("sol", label="test-sol")
    assert wallet.chain == "sol"
    assert wallet.address  # base58 string
    assert not wallet.address.startswith("0x")
    assert wallet.encrypted is True


def test_generate_unsupported_chain(generator):
    """Unsupported chains raise CryptoInputError (caller error, HTTP 400)."""
    from wallet_engine.generator import CryptoInputError

    with pytest.raises(CryptoInputError):
        generator.generate("notachain")


def test_generate_deterministic_with_mnemonic(generator):
    """Same mnemonic + same path => same address (BIP39/BIP44)."""
    mnemonic = (
        "abandon abandon abandon abandon abandon abandon "
        "abandon abandon abandon abandon abandon about"
    )
    w1 = generator.generate("eth", mnemonic=mnemonic)
    w2 = generator.generate("eth", mnemonic=mnemonic)
    assert w1.address == w2.address


def test_generate_safe_dict_omits_secrets(generator):
    """to_safe_dict() must not leak private key or mnemonic."""
    wallet = generator.generate("eth")
    safe = wallet.to_safe_dict()
    assert "private_key_hex" not in safe
    assert "mnemonic" not in safe
    assert safe["has_private_key"] is True
    assert safe["address"] == wallet.address


def test_generate_clear_sensitive(generator):
    """clear_sensitive() wipes key material from the wallet object."""
    wallet = generator.generate("eth")
    assert wallet.private_key_hex
    wallet.clear_sensitive()
    assert wallet.private_key_hex == ""
    assert wallet.mnemonic == ""


# ── Balance check (Vault + balance_fetcher) ─────────────────────────────────


def test_vault_put_and_get(vault):
    """A wallet can be persisted to the vault and retrieved."""
    entry = WalletEntry(id="w1", chain="eth", address="0xabc", label="test")
    assert vault.put(entry) is True
    got = vault.get("w1")
    assert got is not None
    assert got.address == "0xabc"
    assert got.chain == "eth"


def test_vault_get_by_address(vault):
    """Lookup by address returns the matching wallet."""
    vault.put(WalletEntry(id="w1", chain="eth", address="0xabc", label="a"))
    got = vault.get_by_address("0xabc")
    assert got is not None
    assert got.id == "w1"


def test_vault_count_and_list(vault):
    """count() and list() reflect persisted wallets."""
    vault.put(WalletEntry(id="w1", chain="eth", address="0x1", label="a"))
    vault.put(WalletEntry(id="w2", chain="sol", address="0x2", label="b"))
    assert vault.count() == 2
    assert vault.count(chain="eth") == 1
    assert len(vault.list()) == 2


def test_vault_delete(vault):
    """delete() removes a wallet from the vault."""
    vault.put(WalletEntry(id="w1", chain="eth", address="0x1", label="a"))
    assert vault.delete("w1") is True
    assert vault.get("w1") is None


@pytest.mark.asyncio
async def test_balance_fetcher_evm(client, httpx_mock):
    """GET /api/v1/wallet/{address}/balance returns RPC balance for EVM."""
    httpx_mock.add_response(
        url=re.compile(r"https://eth\.llamarpc\.com"),
        json={"jsonrpc": "2.0", "id": 1, "result": "0xde0b6b3a7640000"},  # 1 ETH
        status_code=200,
    )
    resp = await client.get(
        "/api/v1/wallet/0x8b991D96E16a2232174FFACb471966ed67290D4E/balance?chain=eth"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chain"] == "eth"
    assert data["balance"] == "1000000000000000000"
    assert data["balance_decimal"] == 1.0
    assert data["token"] == "ETH"


@pytest.mark.asyncio
async def test_balance_fetcher_unsupported_chain(client):
    """Unsupported chain returns 400."""
    resp = await client.get(
        "/api/v1/wallet/0x8b991D96E16a2232174FFACb471966ed67290D4E/balance?chain=notachain"
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_balance_fetcher_invalid_address(client):
    """Invalid address format returns 400."""
    resp = await client.get("/api/v1/wallet/notanaddress/balance?chain=eth")
    assert resp.status_code == 400


# ── Transaction history (Vault rotations) ───────────────────────────────────


def test_record_rotation(vault):
    """record_rotation() appends a rotation/transaction entry."""
    vault.put(WalletEntry(id="w1", chain="eth", address="0xold", label="a"))
    vault.record_rotation("w1", "0xnew", reason="security")
    rotations = vault.get_rotations("w1")
    assert len(rotations) == 1
    assert rotations[0]["new_address"] == "0xnew"
    assert rotations[0]["reason"] == "security"


def test_get_rotations_empty(vault):
    """get_rotations() returns [] when no history exists."""
    assert vault.get_rotations("nonexistent") == []


def test_rotation_history_ordered(vault):
    """Rotations are returned newest-first."""
    vault.put(WalletEntry(id="w1", chain="eth", address="0x1", label="a"))
    vault.record_rotation("w1", "0x2", reason="first")
    vault.record_rotation("w1", "0x3", reason="second")
    rotations = vault.get_rotations("w1")
    assert len(rotations) == 2
    assert rotations[0]["new_address"] == "0x3"  # newest first


def test_vault_stats(vault):
    """stats() aggregates wallet and rotation counts."""
    vault.put(WalletEntry(id="w1", chain="eth", address="0x1", label="a"))
    vault.record_rotation("w1", "0x2", reason="test")
    stats = vault.stats()
    assert stats["total_wallets"] == 1
    assert stats["rotations"] == 1
    assert stats["by_chain"]["eth"] == 1
