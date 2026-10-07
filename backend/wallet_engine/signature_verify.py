"""Server-side wallet signature verification (EVM personal_sign + Solana Ed25519).

Real cryptographic verification — no stubs. Used by the wallet-analysis
``POST /api/v1/wallet/verify`` endpoint, which backs the WordPress plugin's
wallet-login flow. A signature that does not verify MUST return
``verified: false``; the plugin treats anything else as authenticated.

EVM:  EIP-191 personal_sign recovery via eth-account (ecrecover).
Solana: Ed25519 verify via PyNaCl over the base58-decoded pubkey/signature.
"""

from __future__ import annotations

import base64
import logging

logger = logging.getLogger("wp.signature_verify")

#: Chains where we can verify today. Anything else → explicit unsupported.
_SUPPORTED = {"ethereum", "solana", "base", "arbitrum", "polygon", "bsc", "optimism"}


async def verify_message(chain: str, address: str, message: str, signature: str) -> bool:
    """Verify a wallet signature. Returns True ONLY on cryptographic proof.

    Never raises for bad input — returns False (an invalid signature is a
    normal, expected outcome, not an error).
    """
    chain = (chain or "").lower()
    if chain not in _SUPPORTED:
        logger.warning("signature_verify_unsupported chain=%s", chain)
        return False
    if not address or not signature or not message:
        return False

    if chain == "solana":
        return _verify_solana(address, message, signature)
    return _verify_evm(address, message, signature)


def _verify_evm(address: str, message: str, signature: str) -> bool:
    """EIP-191 personal_sign recovery: signer must equal the claimed address."""
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        sig = signature
        if sig.startswith("0x"):
            sig_bytes = bytes.fromhex(sig[2:])
        else:
            # Some wallets send base64; try hex first, then base64.
            try:
                sig_bytes = bytes.fromhex(sig)
            except ValueError:
                sig_bytes = base64.b64decode(sig)
        if len(sig_bytes) != 65:
            return False
        recovered = Account.recover_message(encode_defunct(text=message), signature=sig_bytes)
        return recovered.lower() == address.lower()
    except Exception as e:
        logger.debug("evm verify failed: %s", e)
        return False


def _verify_solana(address: str, message: str, signature: str) -> bool:
    """Ed25519 verify (Phantom/Solflare signMessage). base58 pubkey + sig."""
    try:
        from nacl.signing import VerifyKey

        pubkey = _b58decode(address)
        if len(pubkey) != 32:
            return False
        sig_bytes = _decode_sig(signature)
        if sig_bytes is None or len(sig_bytes) != 64:
            return False
        VerifyKey(pubkey).verify(message.encode("utf-8"), sig_bytes)
        return True
    except Exception as e:
        logger.debug("solana verify failed: %s", e)
        return False


def _decode_sig(signature: str) -> bytes | None:
    sig = signature.strip()
    try:
        return _b58decode(sig)
    except Exception as exc:
        logger.debug("sig not base58: %s", exc)
    try:
        return base64.b64decode(sig)
    except Exception as exc:
        logger.debug("sig not base64: %s", exc)
        return None


_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58decode(data: str) -> bytes:
    """Minimal base58 decode (Bitcoin/Solana alphabet)."""
    data = data.strip()
    pad = len(data) - len(data.lstrip("1"))
    num = 0
    for ch in data.lstrip("1"):
        idx = _B58_ALPHABET.find(ch)
        if idx < 0:
            raise ValueError(f"invalid base58 char {ch!r}")
        num = num * 58 + idx
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    return b"\x00" * pad + raw
