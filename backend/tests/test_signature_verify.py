"""Tests for wallet_engine/signature_verify.py — real crypto, no network."""

from __future__ import annotations

import base64

import pytest

from wallet_engine.signature_verify import _b58decode, verify_message

# ── EVM (eth_account) ─────────────────────────────────────────────


def _evm_sign(message: str):
    from eth_account import Account
    from eth_account.messages import encode_defunct

    acct = Account.from_key("0x" + "11" * 32)
    signed = acct.sign_message(encode_defunct(text=message))
    return acct.address, signed.signature.hex()


@pytest.mark.asyncio
async def test_evm_valid_signature():
    message = "login to walletpress"
    address, sig = _evm_sign(message)
    assert await verify_message("ethereum", address, message, "0x" + sig) is True


@pytest.mark.asyncio
async def test_evm_wrong_address():
    message = "login"
    _address, sig = _evm_sign(message)
    wrong = "0x" + "ab" * 20
    assert await verify_message("ethereum", wrong, message, "0x" + sig) is False


@pytest.mark.asyncio
async def test_evm_tampered_message():
    address, sig = _evm_sign("original message")
    assert await verify_message("ethereum", address, "tampered", "0x" + sig) is False


@pytest.mark.asyncio
async def test_evm_base64_signature():
    message = "login"
    address, sig = _evm_sign(message)
    sig_b64 = base64.b64encode(bytes.fromhex(sig)).decode()
    assert await verify_message("ethereum", address, message, sig_b64) is True


@pytest.mark.asyncio
async def test_evm_bad_length_signature():
    assert await verify_message("ethereum", "0x" + "11" * 20, "msg", "0x1234") is False


@pytest.mark.asyncio
async def test_evm_garbage_signature():
    assert await verify_message("ethereum", "0x" + "11" * 20, "msg", "0xzzzz") is False


# ── Solana (Ed25519 via PyNaCl) ───────────────────────────────────


def _solana_sign(message: str):
    from nacl.signing import SigningKey

    sk = SigningKey(b"\x01" * 32)
    vk = sk.verify_key
    sig = sk.sign(message.encode("utf-8")).signature
    return _b58encode(bytes(vk)), _b58encode(sig)


_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    num = int.from_bytes(data, "big")
    out = ""
    while num:
        num, rem = divmod(num, 58)
        out = _B58_ALPHABET[rem] + out
    pad = len(data) - len(data.lstrip(b"\x00"))
    return "1" * pad + out


@pytest.mark.asyncio
async def test_solana_valid_signature():
    message = "solana login"
    pubkey, sig = _solana_sign(message)
    assert await verify_message("solana", pubkey, message, sig) is True


@pytest.mark.asyncio
async def test_solana_wrong_signer():
    from nacl.signing import SigningKey

    message = "solana login"
    sk = SigningKey(b"\x01" * 32)
    sk2 = SigningKey(b"\x02" * 32)
    sig = sk.sign(message.encode()).signature
    wrong_pub = _b58encode(bytes(sk2.verify_key))
    assert await verify_message("solana", wrong_pub, message, _b58encode(sig)) is False


@pytest.mark.asyncio
async def test_solana_bad_pubkey_length():
    assert await verify_message("solana", "short", "msg", "sig") is False


@pytest.mark.asyncio
async def test_solana_garbage_sig():
    pubkey = _b58encode(b"\x01" * 32)
    assert await verify_message("solana", pubkey, "msg", "!!!not-valid!!!") is False


# ── input validation ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_chain():
    assert await verify_message("cardano", "addr", "msg", "sig") is False


@pytest.mark.asyncio
async def test_empty_fields():
    assert await verify_message("ethereum", "", "msg", "sig") is False
    assert await verify_message("ethereum", "addr", "", "sig") is False
    assert await verify_message("ethereum", "addr", "msg", "") is False
    assert await verify_message("", "addr", "msg", "sig") is False


# ── base58 helper ─────────────────────────────────────────────────


def test_b58decode_roundtrip():
    data = b"hello world"
    assert _b58decode(_b58encode(data)) == data


def test_b58decode_leading_zeros():
    encoded = "1" + _b58encode(b"\x01")
    assert _b58decode(encoded) == b"\x00\x01"


def test_b58decode_invalid_char():
    with pytest.raises(ValueError, match="invalid base58 char"):
        _b58decode("0OIl")
