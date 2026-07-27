"""Tests: per-chain address encoders and helper utilities."""

import os
import tempfile

os.environ["WP_VAULT_PASSWORD"] = "test-addresses"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_addr_")

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

import hashlib
import pytest
from wallet_engine.chain_addresses import (
    ripemd160_of_sha256,
    crc16_xmodem,
    base58_encode_check,
    cosmos_address,
    xrp_address,
    nano_address,
    algorand_address,
    encode_address,
    XRP_ALPHABET,
)


# ── Low-level helper tests ───────────────────────────────────────


def test_ripemd160_of_sha256():
    result = ripemd160_of_sha256(b"hello")
    expected = hashlib.new("ripemd160", hashlib.sha256(b"hello").digest()).digest()
    assert result == expected
    assert len(result) == 20


def test_ripemd160_of_sha256_empty():
    result = ripemd160_of_sha256(b"")
    assert len(result) == 20


def test_ripemd160_of_sha256_deterministic():
    a = ripemd160_of_sha256(b"test data")
    b = ripemd160_of_sha256(b"test data")
    assert a == b


def test_crc16_xmodem_known():
    """CRC-16/XMODEM of b"123456789" should be 0x31C3."""
    result = crc16_xmodem(b"123456789")
    assert result == 0x31C3, f"Expected 0x31C3, got {hex(result)}"


def test_crc16_xmodem_empty():
    assert crc16_xmodem(b"") == 0


def test_crc16_xmodem_deterministic():
    assert crc16_xmodem(b"hello") == crc16_xmodem(b"hello")
    assert crc16_xmodem(b"hello") != crc16_xmodem(b"world")


def test_base58_encode_check():
    result = base58_encode_check(
        b"\x00\x00\x00", b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    )
    # Three zero bytes should produce three '1' characters (or similar)
    assert isinstance(result, str)
    assert len(result) > 0


def test_base58_encode_check_nonzero():
    payload = b"\x01\x02\x03"
    result = base58_encode_check(
        payload, b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    )
    assert isinstance(result, str)
    assert len(result) > 0
    assert result[0] != "1"  # non-zero bytes should not produce leading '1's


# ── Cosmos address tests ─────────────────────────────────────────


def test_cosmos_address_format():
    # 33-byte compressed secp256k1 pubkey
    pubkey = bytes([0x02]) + b"\x00" * 32
    addr = cosmos_address(pubkey, "cosmos")
    assert addr.startswith("cosmos1")
    assert len(addr) > 40


def test_cosmos_address_custom_hrp():
    pubkey = bytes([0x02]) + b"\x00" * 32
    addr_osmo = cosmos_address(pubkey, "osmo")
    addr_juno = cosmos_address(pubkey, "juno")
    assert addr_osmo.startswith("osmo1")
    assert addr_juno.startswith("juno1")
    assert addr_osmo != addr_juno


def test_cosmos_address_deterministic():
    pubkey = b"\x03" + b"\x01" * 32
    a = cosmos_address(pubkey, "cosmos")
    b = cosmos_address(pubkey, "cosmos")
    assert a == b


def test_cosmos_address_wrong_length():
    # bech32 can handle short inputs, but the result won't be a valid address
    # Just verify it doesn't crash
    result = cosmos_address(b"x" * 5, "cosmos")
    assert isinstance(result, str)
    assert result.startswith("cosmos1")


# ── XRP address tests ────────────────────────────────────────────


def test_xrp_address_format():
    pubkey = bytes([0x02]) + b"\x00" * 32
    addr = xrp_address(pubkey)
    assert addr.startswith("r")
    assert isinstance(addr, str)
    assert len(addr) > 20


def test_xrp_address_deterministic():
    pubkey = bytes([0x03]) + b"\x01" * 32
    assert xrp_address(pubkey) == xrp_address(pubkey)


def test_xrp_alphabet_unique():
    """XRP alphabet should be a valid base58 alphabet (no duplicates)."""
    assert len(set(XRP_ALPHABET)) == len(XRP_ALPHABET)
    assert len(XRP_ALPHABET) == 58


def test_xrp_alphabet_starts_with_r():
    assert XRP_ALPHABET[0:1] == b"r"


# ── Nano address tests ───────────────────────────────────────────


def test_nano_address_format():
    pubkey = b"\x00" * 32
    addr = nano_address(pubkey)
    assert addr.startswith("nano_")
    assert len(addr) > 50


def test_nano_address_length():
    pubkey = b"\x01" * 32
    addr = nano_address(pubkey)
    # nano_ + 60 base32 chars (32 bytes + 5 byte checksum)
    assert len(addr) == 65


def test_nano_address_invalid_length():
    with pytest.raises(ValueError, match="ed25519 pubkey must be 32 bytes"):
        nano_address(b"too_short")


def test_nano_address_deterministic():
    pubkey = b"\x02" * 32
    assert nano_address(pubkey) == nano_address(pubkey)


# ── Algorand address tests ───────────────────────────────────────


def test_algorand_address_format():
    pubkey = b"\x00" * 32
    addr = algorand_address(pubkey)
    # Algorand addresses are 58 base32 chars
    assert len(addr) == 58


def test_algorand_address_deterministic():
    pubkey = b"\x01" * 32
    assert algorand_address(pubkey) == algorand_address(pubkey)


def test_algorand_address_invalid_length():
    with pytest.raises(ValueError, match="ed25519 pubkey must be 32 bytes"):
        algorand_address(b"x" * 10)


# ── Dispatch table tests ─────────────────────────────────────────


def test_encode_address_bech32():
    pubkey = bytes([0x02]) + b"\x00" * 32
    addr = encode_address("bech32", pubkey, "cosmos")
    assert addr.startswith("cosmos1")


def test_encode_address_xrp():
    pubkey = bytes([0x02]) + b"\x00" * 32
    addr = encode_address("xrp", pubkey)
    assert addr.startswith("r")


def test_encode_address_nano():
    pubkey = b"\x00" * 32
    addr = encode_address("nano", pubkey)
    assert addr.startswith("nano_")


def test_encode_address_algorand():
    pubkey = b"\x00" * 32
    addr = encode_address("algorand", pubkey)
    assert len(addr) == 58


def test_encode_address_unknown():
    with pytest.raises(ValueError, match="Unknown address family"):
        encode_address("nonexistent_family", b"data")


def test_encode_address_stellar():
    pubkey = b"\x00" * 32
    addr = encode_address("stellar", pubkey)
    assert addr.startswith("G")
    assert len(addr) == 56


def test_encode_address_tezos():
    pubkey = b"\x00" * 32
    addr = encode_address("tezos", pubkey)
    assert addr.startswith("tz1")


def test_encode_address_ton():
    pubkey = b"\x00" * 32
    addr = encode_address("ton", pubkey)
    assert isinstance(addr, str)
    assert len(addr) > 30


def test_encode_address_filecoin():
    # Use a proper secp256k1 pubkey that coincurve can decompress
    # This is a known valid compressed pubkey (02 prefix + non-zero x coordinate)
    pubkey = bytes.fromhex("0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")
    addr = encode_address("filecoin", pubkey)
    assert addr.startswith("f1")


def test_encode_address_zcash_t():
    pubkey = bytes([0x02]) + b"\x00" * 32
    addr = encode_address("zcash_t", pubkey)
    assert isinstance(addr, str)
    assert len(addr) > 20


def test_adress_encoders_deterministic():
    pubkey = bytes([0x02]) + b"\x01" * 32
    for family, args_fn in [
        ("bech32", (pubkey, "cosmos")),
        ("xrp", (pubkey,)),
        ("nano", (b"\x01" * 32,)),
        ("algorand", (b"\x01" * 32,)),
        ("stellar", (b"\x01" * 32,)),
        ("tezos", (b"\x01" * 32,)),
        ("ton", (b"\x01" * 32,)),
    ]:
        r1 = encode_address(family, *args_fn)
        r2 = encode_address(family, *args_fn)
        assert r1 == r2, f"{family}: non-deterministic output"


# ── ADDRESS_ENCODERS dispatch map tests ──────────────────────────


from wallet_engine.chain_addresses import ADDRESS_ENCODERS


def test_address_encoders_map_has_keys():
    assert "atom" in ADDRESS_ENCODERS
    assert "osmo" in ADDRESS_ENCODERS
    assert "xlm" in ADDRESS_ENCODERS
    assert "xrp" in ADDRESS_ENCODERS
    assert "ton" in ADDRESS_ENCODERS
    assert "algo" in ADDRESS_ENCODERS


def test_address_encoders_family_is_string():
    for key, (family, _) in ADDRESS_ENCODERS.items():
        assert isinstance(family, str), f"{key}: family should be string, got {type(family)}"
