"""Property-based tests for wallet_engine critical paths.

Uses Hypothesis to validate:
1. Address/key round-trip properties (EVM and Solana)
2. Deterministic signature generation and verification
3. Invalid input handling across signing/key code paths

Run with:
    pytest tests/test_property_based.py -v
    pytest tests/test_property_based.py -v --hypothesis-profile=ci
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

# Hypothesis is a dev dependency; skip gracefully if missing.
try:
    import hypothesis  # noqa: F401

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

from wallet_engine.signature_verify import _b58decode, verify_message

# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
# Valid base58 characters as a list for hypothesis
_B58_CHAR_LIST = list(_B58_ALPHABET)


def _b58encode(data: bytes) -> str:
    num = int.from_bytes(data, "big")
    out = ""
    while num:
        num, rem = divmod(num, 58)
        out = _B58_ALPHABET[rem] + out
    pad = len(data) - len(data.lstrip(b"\x00"))
    return "1" * pad + out


_valid_hex_chars = st.characters(
    whitelist_categories=("Nd",), min_codepoint=0, max_codepoint=9
).filter(lambda c: c in "0123456789abcdefABCDEF")
_hex_nibble = st.sampled_from(list("0123456789abcdef"))


def _evm_sign(message: str):
    from eth_account import Account
    from eth_account.messages import encode_defunct

    acct = Account.from_key("0x" + "11" * 32)
    signed = acct.sign_message(encode_defunct(text=message))
    return acct.address, signed.signature.hex()


def _solana_sign(message: str):
    from nacl.signing import SigningKey

    sk = SigningKey(b"\x01" * 32)
    vk = sk.verify_key
    sig = sk.sign(message.encode("utf-8")).signature
    return _b58encode(bytes(vk)), _b58encode(sig)


# ---------------------------------------------------------------------------
# 1. Address/key round-trip properties
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestAddressKeyRoundtrip:
    """Round-trip: encode/decode must be inverse operations."""

    @given(st.binary(min_size=1, max_size=64))
    @settings(deadline=1000, max_examples=200)
    def test_b58_roundtrip(self, data: bytes):
        encoded = _b58encode(data)
        decoded = _b58decode(encoded)
        assert decoded == data

    @given(st.binary(min_size=1, max_size=64))
    @settings(deadline=1000, max_examples=200)
    def test_b58_leading_zeros_roundtrip(self, data: bytes):
        # Prepend zero bytes to test padding behavior
        padded = b"\x00" * 3 + data
        encoded = _b58encode(padded)
        decoded = _b58decode(encoded)
        assert decoded == padded

    @given(st.text(min_size=1, max_size=200, alphabet=_B58_CHAR_LIST))
    @settings(deadline=1000, max_examples=200)
    def test_valid_b58_decode_inverse(self, encoded: str):
        # Any valid base58 string decodes to bytes; re-encoding should match.
        decoded = _b58decode(encoded)
        assert _b58encode(decoded) == encoded


# ---------------------------------------------------------------------------
# 2. Deterministic signature properties
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestDeterministicSignatures:
    """Signing/verification must be deterministic and correct."""

    @given(st.text(min_size=1, max_size=500))
    @settings(deadline=2000, max_examples=100)
    async def test_evm_sign_verify_deterministic(self, message: str):
        address, sig = _evm_sign(message)
        # Same inputs → same verification result on every call.
        r1 = await verify_message("ethereum", address, message, "0x" + sig)
        r2 = await verify_message("ethereum", address, message, "0x" + sig)
        assert r1 is True
        assert r1 == r2

    @given(st.text(min_size=1, max_size=500))
    @settings(deadline=2000, max_examples=100)
    async def test_solana_sign_verify_deterministic(self, message: str):
        pubkey, sig = _solana_sign(message)
        r1 = await verify_message("solana", pubkey, message, sig)
        r2 = await verify_message("solana", pubkey, message, sig)
        assert r1 is True
        assert r1 == r2

    @given(st.text(min_size=1, max_size=500))
    @settings(deadline=2000, max_examples=100)
    async def test_evm_wrong_message_rejects(self, message: str):
        address, sig = _evm_sign(message)
        # Even one character changed must reject.
        tampered = message + "x"
        assert await verify_message("ethereum", address, tampered, "0x" + sig) is False

    @given(st.text(min_size=1, max_size=500))
    @settings(deadline=2000, max_examples=100)
    async def test_solana_wrong_message_rejects(self, message: str):
        pubkey, sig = _solana_sign(message)
        tampered = message + "x"
        assert await verify_message("solana", pubkey, tampered, sig) is False


# ---------------------------------------------------------------------------
# 3. Invalid-input handling
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestInvalidInputHandling:
    """verify_message must never raise on bad input; must return False."""

    @given(st.text(min_size=0, max_size=100))
    @settings(deadline=1000, max_examples=200)
    async def test_empty_or_whitespace_inputs_never_raise(self, text: str):
        # Empty/None-like values should not raise; they should return False.
        result = await verify_message("ethereum", text, text, text)
        assert result is False

    @given(
        chain=st.sampled_from(
            ["ethereum", "solana", "base", "arbitrum", "polygon", "bsc", "optimism"]
        ),
        bad_addr=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(blacklist_characters="0123456789abcdefABCDEFx"),
        ),
        bad_sig=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(blacklist_characters="0123456789abcdefABCDEFx"),
        ),
    )
    @settings(deadline=1000, max_examples=150)
    async def test_garbage_inputs_return_false(self, chain: str, bad_addr: str, bad_sig: str):
        # Completely invalid characters must not crash the verifier.
        result = await verify_message(chain, bad_addr, "msg", bad_sig)
        assert result is False

    @given(st.binary(min_size=0, max_size=128))
    @settings(deadline=1000, max_examples=200)
    def test_b58decode_invalid_chars_raise(self, data: bytes):
        # Inject an invalid base58 character and confirm ValueError.
        valid = _b58encode(data)
        if valid:
            # Replace first char with invalid '0'
            invalid = "0" + valid[1:] if valid[0] != "0" else "O" + valid[1:]
            with pytest.raises(ValueError, match="invalid base58 char"):
                _b58decode(invalid)
