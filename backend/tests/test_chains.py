"""Tests: chain definitions are valid and generate keys."""
import os

os.environ["WP_VAULT_PASSWORD"] = "test"

from core.config import cfg
cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from wallet_engine.chains import CHAINS, ChainFamily, validate_address
from wallet_engine.generator import WalletGenerator

gen = WalletGenerator()


def test_all_chains_have_required_fields():
    for key, c in CHAINS.items():
        assert c.name, f"{key}: missing name"
        assert c.symbol, f"{key}: missing symbol"
        assert c.family in ChainFamily, f"{key}: invalid family {c.family}"
        assert c.hd_path, f"{key}: missing hd_path"
        assert c.curve, f"{key}: missing curve"
        assert c.native_token, f"{key}: missing native_token"


def test_all_chains_generate_valid_wallet():
    for key in CHAINS:
        if key == "xmr":
            continue  # requires monero package
        w = gen.generate(key)
        assert w.address, f"{key}: empty address"
        assert w.private_key_hex, f"{key}: empty private key"
        assert w.chain == key
        assert w.created_at > 0


def test_deterministic_addresses():
    mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    for key in ["eth", "sol", "btc", "trx", "bsc", "polygon", "base"]:
        w1 = gen.generate(key, mnemonic=mnemonic)
        w2 = gen.generate(key, mnemonic=mnemonic)
        assert w1.address == w2.address, f"{key}: non-deterministic address"


def test_address_validation():
    known = {
        "eth": "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
        "sol": "7EcDhSYGXxyscszYEp35KHN8vvw3svAuLKTzXwCFLtGQ",
        "btc": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
        "trx": "TXYZopYRdj2f9GkfC1mSXGJj1dCAg5XtKn",
        "bsc": "0x8894e0a0c962cb723c1976a4421c95949be2d4e3",
        "polygon": "0x0000000000000000000000000000000000001010",
        "base": "0x4200000000000000000000000000000000000006",
    }
    for key, addr in known.items():
        assert validate_address(key, addr), f"{key}: known good address fails validation"


def test_clear_sensitive():
    w = gen.generate("eth")
    pk = w.private_key_hex
    assert pk, "private key should exist before clear"
    w.clear_sensitive()
    assert w.private_key_hex == "", "private key should be empty after clear"


def test_context_manager_zeroes_key():
    with gen.generate("eth") as w:
        pk = w.private_key_hex
        assert pk, "private key should exist inside context"
    assert w.private_key_hex == "", "private key should be zeroed after context exit"


def test_eip55_checksum():
    w = gen.generate("eth", mnemonic="abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about")
    addr = w.address
    assert addr == "0x9858EfFD232B4033E47d90003D41EC34EcaEda94", f"Expected known EIP55 address, got {addr}"


def test_solana_base58():
    w = gen.generate("sol", mnemonic="abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about")
    assert w.address.startswith("H") or w.address.isprintable()
    assert len(w.address) == 44, f"Expected 44-char base58 Solana address, got {len(w.address)}: {w.address}"
