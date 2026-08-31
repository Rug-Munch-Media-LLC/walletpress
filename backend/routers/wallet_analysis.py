"""Wallet Analysis Router — balance checking + signature verification.

Walletpress is a STANDALONE self-hosted wallet management platform. It has
NO dependency on RMI/rugmunch services — everything here works from public
blockchain data and local cryptography only:

  * ``GET  /{address}/balance``  — real RPC balance lookup (public data).
  * ``POST /verify``             — real cryptographic signature verification
                                   (EVM EIP-191 personal_sign recovery,
                                   Solana Ed25519). Backs wallet-login.

Removed as AI slop (2026-08-31): /analyze, /transactions (returned
fabricated empty skeletons), /scan (proxied a foreign RMI dependency with a
nonexistent path). Wallet RISK scanning lives in rmi-backend's unified
scanner — a separate product surface, not this app's job.

Trust: All data comes from public blockchains or local cryptography.
We don't fabricate results.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from wallet_engine.chains import CHAINS, validate_address
from wallet_engine.signature_verify import verify_message

logger = logging.getLogger("wp.wallet_analysis")

router = APIRouter(prefix="/api/v1/wallet", tags=["Wallet Analysis"])


@router.get("/{address}/balance")
async def get_balance(address: str, chain: str = "solana"):
    """Get wallet balance from the blockchain.

    Uses public RPC endpoints. No API key required — all data is public.
    Supports Solana, Ethereum, and EVM-compatible chains.

    Trust: Balances come directly from the blockchain via public RPC.
    We never modify or cache balance data longer than 60 seconds.
    """
    chain_info = CHAINS.get(chain.lower())
    if not chain_info:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")

    if not validate_address(chain, address):
        raise HTTPException(status_code=400, detail="Invalid address format")

    from .balance_fetcher import fetch_balance

    try:
        result = await fetch_balance(chain, address)
        return {
            "address": address,
            "chain": chain,
            "balance": result.get("balance", "0"),
            "balance_decimal": result.get("balance_decimal", 0),
            "balance_usd": result.get("balance_usd", 0),
            "token": chain_info.native_token,
            "source": result.get("source", "rpc"),
        }
    except Exception as e:
        return {
            "address": address,
            "chain": chain,
            "balance": "0",
            "balance_decimal": 0,
            "balance_usd": 0,
            "token": chain_info.native_token,
            "error": str(e),
            "note": "RPC lookup failed. Public blockchain data may be unavailable.",
        }


@router.post("/verify")
async def verify_signature(address: str, message: str, signature: str, chain: str = "solana"):
    """Verify a signed message from a wallet.

    Cryptographically proves that the wallet owner signed a specific
    message. This is the same mechanism used for Web3 authentication.

    Trust: Signature verification is done entirely server-side using
    standard cryptographic primitives (eth-account ecrecover for EVM,
    PyNaCl Ed25519 for Solana). We CANNOT forge signatures, and an
    invalid signature returns ``verified: false`` — never an exception
    shaped like success.
    """
    chain_info = CHAINS.get(chain.lower())
    if not chain_info:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")

    if not validate_address(chain, address):
        raise HTTPException(status_code=400, detail="Invalid address format")

    verified = await verify_message(chain, address, message, signature)

    return {
        "verified": bool(verified),
        "address": address,
        "chain": chain,
        "message": message[:50] + "..." if len(message) > 50 else message,
    }
