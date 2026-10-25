"""Payment-gate policy for the x402 marketplace.

Everything that decides WHETHER an order may be fulfilled lives here: prepaid
key verification, the x402-coffer facilitator calls, and the free-tier 402
body. Persistence is core.x402_store; HTTP wiring is x402_service.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

import coffer_client

logger = logging.getLogger("x402")


def verify_credits(api_key: str) -> bool:
    """Server-verify a prepaid API key against the local KeyStore.

    Client-supplied claims are never trusted: the key must exist (unhashed)
    in the server-side key store for the credits payment method to apply.
    """
    if not api_key:
        return False
    try:
        from core.auth import get_key_store

        return get_key_store().verify(api_key) is not None
    except Exception:
        logger.exception("Credit verification failed")
        return False


async def verify_with_coffer(order_id: str, chain: str, tx: str, expected_usd: float) -> dict:
    """Verify a reported on-chain payment via the x402-coffer facilitator.

    Fail-closed: raises coffer_client.CofferUnavailable when the coffer is
    unreachable, so the caller refuses the order with HTTP 402.
    """
    if expected_usd <= 0:
        return {"verified": True, "reason": "free", "network": "", "asset": ""}
    if not tx:
        return {"verified": False, "reason": "No payment tx provided"}
    network, asset = coffer_client.resolve_network_asset(chain)
    logger.info(
        "coffer_verify_start order_id=%s chain=%s expected_usd=%s",
        order_id,
        chain,
        expected_usd,
    )
    return await coffer_client.verify_payment(
        payment_id=order_id,
        tx_hash=tx,
        network=network,
        asset=asset,
        amount_usd=expected_usd,
    )


async def settle_with_coffer(
    order_id: str, chain: str, tx: str, expected_usd: float
) -> dict | None:
    """Best-effort settlement of a verified payment (EIP-3009 authorizations).

    Verify is authoritative; a settlement failure is logged, never a reason to
    withhold an order whose payment is already verified.
    """
    try:
        network, asset = coffer_client.resolve_network_asset(chain)
        return await coffer_client.settle_payment(
            payment_id=order_id,
            tx_hash=tx,
            network=network,
            asset=asset,
            amount_usd=expected_usd,
        )
    except coffer_client.CofferUnavailable:
        logger.warning(
            "coffer_settle_unavailable order_id=%s - verify already passed; fulfilling",
            order_id,
        )
        return None


def free_tier_rejection(
    *, chain: str, total_usd: float, free_used: int, limit: int, pay_to: str
) -> HTTPException:
    """Build the 402 body shown when the free tier is exhausted."""
    return HTTPException(
        status_code=402,
        detail={
            "error": "Payment required",
            "reason": f"Free tier exhausted ({free_used}/{limit} wallets used)",
            "amount_usd": total_usd,
            "pay_to": pay_to,
            "chain": chain,
            "token": "USDC",
            "instructions": f"Send ${total_usd} USDC on {chain.upper()} to {pay_to}",
        },
    )


async def authorize(
    *,
    api_key: str,
    payment_tx: str,
    order_id: str,
    chain: str,
    count: int,
    total_usd: float,
    client_ip: str,
    free_used: int,
    price_per_wallet: float,
    min_order_usd: float,
    free_wallets: int,
    pay_to: str,
) -> tuple[str, dict | None]:
    """Decide the payment method, or raise the error that refuses the order.

    Policy is passed in rather than imported, so the facade stays the single
    owner of its configuration (and tests can monkeypatch it there).
    """
    # Minimum order size is enforced unconditionally: no client bypasses it by
    # omitting payment info or claiming credits.
    if total_usd < min_order_usd:
        min_count = max(1, int(-(-min_order_usd // price_per_wallet)))
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Order below minimum",
                "required_min_usd": min_order_usd,
                "requested_usd": total_usd,
                "hint": f"Increase wallet count to at least {min_count} wallets.",
            },
        )

    if api_key:
        if not verify_credits(api_key):
            raise HTTPException(status_code=402, detail="Invalid or unknown prepaid API key")
        return "credits", None

    if payment_tx:
        try:
            verification = await verify_with_coffer(order_id, chain, payment_tx, total_usd)
        except coffer_client.CofferUnavailable as exc:
            logger.error("Coffer verification unavailable for order %s: %s", order_id, exc)
            raise HTTPException(
                status_code=402,
                detail="Payment verification unavailable - please retry shortly",
            ) from exc
        except ValueError as exc:  # unsupported payment chain
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not verification.get("verified"):
            reason = verification.get("reason") or "not verified"
            raise HTTPException(status_code=402, detail=f"Payment verification failed: {reason}")
        network, asset = coffer_client.resolve_network_asset(chain)
        ok, match_reason = coffer_client.confirm_matches_order(
            verification, network=network, asset=asset, amount_usd=total_usd
        )
        if not ok:
            logger.warning("Coffer confirm-match failed for order %s: %s", order_id, match_reason)
            raise HTTPException(status_code=402, detail=f"Payment verification failed: {match_reason}")
        return "onchain", await settle_with_coffer(order_id, chain, payment_tx, total_usd)

    if free_used + count > free_wallets:
        raise free_tier_rejection(
            chain=chain,
            total_usd=total_usd,
            free_used=free_used,
            limit=free_wallets,
            pay_to=pay_to,
        )
    return "free", None
