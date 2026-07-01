"""x402 payment verification — multi-chain USDC via PayAI facilitator.

Replicates the RMI backend's payment verification system:
  https://facilitator.payai.network/verify

Supports: Solana, Base, Polygon, Arbitrum, Ethereum — all USDC.
No API key needed. Sends the x402 v2 payload, gets back isValid + tx data.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger("wp.x402_verify")

FACILITATOR_URL = os.getenv("WP_X402_FACILITATOR_URL", "https://facilitator.payai.network/verify")
PAY_TO = os.getenv("WP_PAYMENT_ADDRESS", "G1uZFfsdxK2PuH2Em5LhRkEcptxHWe4vy5BZak67QyKv")

# Chain config: network identifier, USDC mint/contract, default pay-to address
CHAIN_CONFIG: dict[str, dict[str, str]] = {
    "sol": {
        "network": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
        "usdc": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "pay_to": os.getenv("WP_PAYMENT_ADDRESS_SOL", "G1uZFfsdxK2PuH2Em5LhRkEcptxHWe4vy5BZak67QyKv"),
    },
    "base": {
        "network": "eip155:8453",
        "usdc": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "pay_to": os.getenv("WP_PAYMENT_ADDRESS_BASE", "0x1E3AC01d0fdb976179790BDD02823196A92705C9"),
    },
    "polygon": {
        "network": "eip155:137",
        "usdc": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "pay_to": os.getenv("WP_PAYMENT_ADDRESS_POLYGON", "0x1E3AC01d0fdb976179790BDD02823196A92705C9"),
    },
    "arbitrum": {
        "network": "eip155:42161",
        "usdc": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "pay_to": os.getenv("WP_PAYMENT_ADDRESS_ARBITRUM", "0x1E3AC01d0fdb976179790BDD02823196A92705C9"),
    },
    "eth": {
        "network": "eip155:1",
        "usdc": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "pay_to": os.getenv("WP_PAYMENT_ADDRESS_ETH", "0x1E3AC01d0fdb976179790BDD02823196A92705C9"),
    },
}

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30)
    return _client


def get_supported_chains() -> list[str]:
    return list(CHAIN_CONFIG.keys())


def get_pay_to(chain: str) -> str:
    cfg = CHAIN_CONFIG.get(chain)
    return cfg["pay_to"] if cfg else PAY_TO


async def verify_usdc_payment(chain: str, payment_tx: str, expected_usd: float) -> dict:
    """Verify a USDC payment on any supported chain via PayAI facilitator.

    Args:
        chain: Chain key ('sol', 'base', 'polygon', 'arbitrum', 'eth')
        payment_tx: Transaction signature/hash
        expected_usd: Expected USD amount

    Returns:
        dict with keys: verified (bool), reason (str), tx_hash (str),
        payer (str), amount (float)
    """
    if expected_usd <= 0:
        return {"verified": True, "reason": "free", "tx_hash": "", "payer": "", "amount": 0}
    if not payment_tx:
        return {"verified": False, "reason": "No payment tx provided", "tx_hash": "", "payer": "", "amount": 0}

    chain_cfg = CHAIN_CONFIG.get(chain)
    if not chain_cfg:
        return {"verified": False, "reason": f"Unsupported chain: {chain}", "tx_hash": payment_tx, "payer": "", "amount": 0}

    network = chain_cfg["network"]
    usdc_address = chain_cfg["usdc"]
    pay_to = chain_cfg["pay_to"]

    payload = {
        "x402Version": 2,
        "accepted": {
            "scheme": "exact",
            "network": network,
            "asset": f"{network}:{usdc_address}" if chain != "sol" else f"solana:{usdc_address}",
            "amount": str(expected_usd),
            "payTo": pay_to,
            "maxTimeoutSeconds": 300,
        },
        "paymentTx": payment_tx,
    }

    body = {
        "x402Version": 2,
        "paymentPayload": payload,
        "paymentRequirements": {
            "x402Version": 2,
            "scheme": "exact",
            "network": network,
            "asset": f"{network}:{usdc_address}" if chain != "sol" else f"solana:{usdc_address}",
            "amount": str(expected_usd),
            "payTo": pay_to,
            "maxTimeoutSeconds": 300,
        },
    }

    try:
        client = await get_client()
        resp = await client.post(FACILITATOR_URL, json=body)
        data = resp.json() if resp.content else {}
    except httpx.TimeoutException:
        logger.error("x402 PayAI verification timed out")
        return {"verified": False, "reason": "Verification service timeout", "tx_hash": payment_tx, "payer": "", "amount": 0}
    except httpx.RequestError as e:
        logger.error(f"x402 PayAI verification failed: {e}")
        return {"verified": False, "reason": f"Verification service error: {e}", "tx_hash": payment_tx, "payer": "", "amount": 0}
    except json.JSONDecodeError:
        logger.error(f"x402 PayAI returned non-JSON: {resp.status_code}")
        return {"verified": False, "reason": "Invalid response from verification service", "tx_hash": payment_tx, "payer": "", "amount": 0}

    if data.get("isValid"):
        result = {
            "verified": True,
            "reason": data.get("invalidReason", "verified"),
            "tx_hash": data.get("tx_hash", payment_tx),
            "payer": data.get("payer", ""),
            "amount": float(data.get("amount", expected_usd)),
        }
        logger.info(f"x402 payment verified: chain={chain} tx={payment_tx[:16]}... amount=${expected_usd}")
        return result

    reason = data.get("invalidReason", "unknown")
    message = data.get("invalidMessage", "")
    logger.warning(f"x402 payment rejected: chain={chain} tx={payment_tx[:16]}... reason={reason}")
    return {"verified": False, "reason": f"{reason}: {message}", "tx_hash": payment_tx, "payer": "", "amount": 0}
