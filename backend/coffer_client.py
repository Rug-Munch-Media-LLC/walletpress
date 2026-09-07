#!/usr/bin/env python3
"""WalletPress x402-coffer facilitator client — server-side payment verification.

Merchant half of the coffer wire contract. WalletPress reaches a self-hosted
x402-coffer instance (configured with the treasury receiving wallets) and asks
it to verify / settle the on-chain payments clients report:

    POST {X402_FACILITATOR_URL}/v1/x402/verify   — verify a reported payment
    POST {X402_FACILITATOR_URL}/v1/x402/settle   — settle an EIP-3009 authorization

Fail-closed by design:

* ``X402_FACILITATOR_URL`` unset, or the coffer unreachable / timing out after
  retries, raises :class:`CofferUnavailable`. Callers translate that into HTTP
  402 so nothing is ever fulfilled on an unverifiable payment.
* A reachable coffer that rejects the payment returns ``verified: False`` /
  ``settled: False`` — HTTP 200-plus semantics, never an exception.

Local policy stays ABOVE the facilitator: minimum order size, per-client
free-tier tracking and KeyStore credit auth live in the caller, and
:func:`confirm_matches_order` re-checks the coffer's echoed network / asset /
amount against the quoted order before any keys are returned (mirroring the
pry-scraper billing confirm pattern where the invoice record's recipient,
amount and asset must match the verified payment).
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

logger = logging.getLogger("wp.coffer")

VERIFY_PATH = "/v1/x402/verify"
SETTLE_PATH = "/v1/x402/settle"

#: Total HTTP attempts per call (1 + retries) and backoff between them.
MAX_ATTEMPTS = int(os.getenv("X402_FACILITATOR_MAX_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = 0.1
REQUEST_TIMEOUT = float(os.getenv("X402_FACILITATOR_TIMEOUT", "10.0"))

#: USDC is 6-decimal on every walletpress-supported chain.
USDC_DECIMALS = 6

#: Chain key -> canonical x402 v2 network / asset identifiers (USDC).
CHAIN_CONFIG: dict[str, dict[str, str]] = {
    "sol": {
        "network": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
        "asset": "solana:EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    },
    "base": {
        "network": "eip155:8453",
        "asset": "eip155:8453:0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    },
    "polygon": {
        "network": "eip155:137",
        "asset": "eip155:137:0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
    },
    "arbitrum": {
        "network": "eip155:42161",
        "asset": "eip155:42161:0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    },
    "eth": {
        "network": "eip155:1",
        "asset": "eip155:1:0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    },
}


class CofferError(Exception):
    """Base error for facilitator interactions."""


class CofferUnavailable(CofferError):
    """Coffer is unreachable / misconfigured — callers must fail closed (402)."""


def resolve_network_asset(chain: str) -> tuple[str, str]:
    """Return the canonical (network, asset) x402 identifiers for a chain key.

    Raises:
        ValueError: for chain keys walletpress does not accept USDC payments on.
    """
    entry = CHAIN_CONFIG.get(chain.lower())
    if entry is None:
        supported = ", ".join(sorted(CHAIN_CONFIG))
        raise ValueError(f"Unsupported payment chain: {chain!r} (supported: {supported})")
    return entry["network"], entry["asset"]


def _facilitator_base_url() -> str:
    """Coffer base URL. Read live from env so tests / operators can switch it."""
    url = os.getenv("X402_FACILITATOR_URL", "")
    if not url:
        # Config mirror (core/config.py reads the same variable at import time).
        from core.config import cfg

        url = cfg.x402_facilitator_url
    return url.rstrip("/")


def _auth_headers() -> dict[str, str]:
    """Optional merchant auth for coffer deployments behind an auth proxy."""
    key = os.getenv("X402_MERCHANT_KEY", "")
    if not key:
        from core.config import cfg

        key = cfg.x402_merchant_key
    return {"Authorization": f"Bearer {key}"} if key else {}


def _build_payload(
    payment_id: str,
    tx_hash: str,
    network: str,
    asset: str,
    amount_usd: float,
) -> dict:
    if not payment_id or not tx_hash:
        raise ValueError("payment_id and tx_hash are required")
    if not amount_usd or amount_usd <= 0:
        raise ValueError("amount_usd must be a positive number")
    return {
        "payment_id": payment_id,
        "tx_hash": tx_hash,
        "network": network,
        "asset": asset,
        "amount_usd": float(amount_usd),
    }


async def _post_json(path: str, payload: dict) -> httpx.Response:
    """POST to the coffer with retry. Transport errors / 5xx fail closed."""
    base = _facilitator_base_url()
    if not base:
        raise CofferUnavailable(
            "X402_FACILITATOR_URL is not configured — refusing to verify payments"
        )
    url = f"{base}{path}"
    headers = _auth_headers()
    last_error: CofferUnavailable | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code < 500:
                return resp
            last_error = CofferUnavailable(f"facilitator HTTP {resp.status_code} on {path}")
        except httpx.TimeoutException as exc:
            last_error = CofferUnavailable(f"facilitator timed out on {path}: {exc}")
        except httpx.RequestError as exc:
            last_error = CofferUnavailable(f"facilitator unreachable on {path}: {exc}")
        if attempt < MAX_ATTEMPTS - 1:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
    assert last_error is not None
    raise last_error


async def verify_payment(
    payment_id: str,
    tx_hash: str,
    network: str,
    asset: str,
    amount_usd: float,
) -> dict:
    """Verify a reported on-chain payment against the coffer.

    Returns:
        ``{"verified": True, ...}`` on a coffer-confirmed payment, or
        ``{"verified": False, "reason", "http_status"}`` when the coffer is
        reachable but rejects the payment. Raises :class:`CofferUnavailable`
        when the coffer cannot be reached — the caller MUST fail closed.
    """
    payload = _build_payload(payment_id, tx_hash, network, asset, amount_usd)
    resp = await _post_json(VERIFY_PATH, payload)
    try:
        data = resp.json()
    except ValueError as exc:
        raise CofferUnavailable(
            f"facilitator returned non-JSON on {VERIFY_PATH}: {resp.status_code}"
        ) from exc

    if resp.status_code == 200 and data.get("verified"):
        logger.info(
            "coffer_verify_ok payment_id=%s tx=%s amount_usd=%s",
            payment_id,
            str(tx_hash)[:16],
            amount_usd,
        )
        return {
            "verified": True,
            "reason": str(data.get("reason") or ""),
            "http_status": 200,
            **{
                k: data.get(k)
                for k in (
                    "payment_id",
                    "transaction",
                    "network",
                    "asset",
                    "amount_atomic",
                    "signer",
                    "settlement",
                    "facilitator",
                )
            },
        }

    reason = str(data.get("error") or data.get("reason") or "")
    logger.warning(
        "coffer_verify_rejected payment_id=%s reason=%s status=%s",
        payment_id,
        reason or "unknown",
        resp.status_code,
    )
    return {
        "verified": False,
        "reason": reason or f"payment rejected (HTTP {resp.status_code})",
        "http_status": resp.status_code,
    }


async def settle_payment(
    payment_id: str,
    tx_hash: str,
    network: str,
    asset: str,
    amount_usd: float,
) -> dict:
    """Settle a verified payment (EIP-3009 authorizations move funds on settle).

    Safe to call after :func:`verify_payment` reports ``verified``. Returns
    ``{"settled": True, ...}`` on HTTP 2xx unless the body explicitly reports
    a failure; raises :class:`CofferUnavailable` only when the coffer is
    unreachable.
    """
    payload = _build_payload(payment_id, tx_hash, network, asset, amount_usd)
    resp = await _post_json(SETTLE_PATH, payload)
    try:
        data = resp.json()
    except ValueError as exc:
        raise CofferUnavailable(
            f"facilitator returned non-JSON on {SETTLE_PATH}: {resp.status_code}"
        ) from exc

    receipt = data if isinstance(data, dict) else {}
    explicit_failure = receipt.get("success") is False or receipt.get("settled") is False
    if 200 <= resp.status_code < 300 and not explicit_failure:
        logger.info("coffer_settle_ok payment_id=%s", payment_id)
        return {
            "settled": True,
            "reason": str(receipt.get("reason") or ""),
            "http_status": resp.status_code,
            "receipt": receipt,
        }
    reason = str(receipt.get("error") or receipt.get("reason") or "")
    logger.warning(
        "coffer_settle_rejected payment_id=%s reason=%s status=%s",
        payment_id,
        reason or "unknown",
        resp.status_code,
    )
    return {
        "settled": False,
        "reason": reason or f"settlement rejected (HTTP {resp.status_code})",
        "http_status": resp.status_code,
        "receipt": receipt,
    }


def confirm_matches_order(
    verification: dict,
    *,
    network: str,
    asset: str,
    amount_usd: float,
) -> tuple[bool, str]:
    """Local confirm-match mirror: the verified payment must match the order.

    The coffer's facilitator binds the recipient to the treasury payTo
    on-chain; here we additionally re-check that the echoed network, asset and
    paid amount match the order we quoted (mirrors pry-scraper's
    billing_subscription confirm, where the invoice record's recipient +
    amount + asset must match before anything is activated). Echo fields the
    facilitator does not return are skipped; any returned field that
    contradicts the order fails the match.

    Returns ``(ok, reason)``.
    """
    echoed_network = str(verification.get("network") or "")
    if echoed_network and echoed_network.lower() != network.lower():
        return False, f"network mismatch: paid {echoed_network}, expected {network}"
    echoed_asset = str(verification.get("asset") or "")
    if echoed_asset and echoed_asset.lower() != asset.lower():
        return False, f"asset mismatch: paid {echoed_asset}, expected {asset}"
    echoed_atomic = verification.get("amount_atomic")
    if echoed_atomic not in (None, ""):
        try:
            paid_atomic = int(echoed_atomic)
        except (TypeError, ValueError):
            return False, f"facilitator returned non-numeric amount_atomic: {echoed_atomic!r}"
        expected_atomic = round(amount_usd * (10**USDC_DECIMALS))
        if paid_atomic < expected_atomic:
            return (
                False,
                f"underpayment: paid {paid_atomic} atoms, expected >= {expected_atomic}",
            )
    return True, ""
