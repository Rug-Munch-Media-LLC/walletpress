"""Tests for backend/coffer_client.py + x402_service coffer payment gate (respx-mocked)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx
import pytest
import respx

import coffer_client as cc
import x402_service as xs

COFFER = "https://coffer.test"
VERIFY_URL = f"{COFFER}/v1/x402/verify"
SETTLE_URL = f"{COFFER}/v1/x402/settle"

SOL_NETWORK = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
SOL_ASSET = "solana:EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


# ── resolve_network_asset ────────────────────────────────────────────


def test_resolve_network_asset_mapping():
    assert cc.resolve_network_asset("sol") == (SOL_NETWORK, SOL_ASSET)
    assert cc.resolve_network_asset("base")[0] == "eip155:8453"
    assert cc.resolve_network_asset("ETH")[0] == "eip155:1"  # case-insensitive


def test_resolve_network_asset_unsupported():
    with pytest.raises(ValueError, match="Unsupported payment chain"):
        cc.resolve_network_asset("cardano")


# ── confirm_matches_order ────────────────────────────────────────────


def test_confirm_matches_order_exact():
    v = {"network": SOL_NETWORK, "asset": SOL_ASSET, "amount_atomic": "1000000"}
    ok, reason = cc.confirm_matches_order(v, network=SOL_NETWORK, asset=SOL_ASSET, amount_usd=1.0)
    assert ok
    assert not reason


def test_confirm_matches_order_skips_missing_echo():
    # A facilitator that returns no echo fields must not fail the match.
    ok, reason = cc.confirm_matches_order({}, network=SOL_NETWORK, asset=SOL_ASSET, amount_usd=1.0)
    assert ok
    assert not reason


def test_confirm_matches_order_overpayment_allowed():
    v = {"network": SOL_NETWORK, "asset": SOL_ASSET, "amount_atomic": "2500000"}
    ok, _ = cc.confirm_matches_order(v, network=SOL_NETWORK, asset=SOL_ASSET, amount_usd=1.0)
    assert ok


def test_confirm_matches_order_rejects_asset_mismatch():
    v = {"network": SOL_NETWORK, "asset": "solana:0xDEAD"}
    ok, reason = cc.confirm_matches_order(v, network=SOL_NETWORK, asset=SOL_ASSET, amount_usd=1.0)
    assert not ok
    assert "asset mismatch" in reason


def test_confirm_matches_order_rejects_underpayment():
    v = {"network": SOL_NETWORK, "asset": SOL_ASSET, "amount_atomic": "500000"}
    ok, reason = cc.confirm_matches_order(v, network=SOL_NETWORK, asset=SOL_ASSET, amount_usd=1.0)
    assert not ok
    assert "underpayment" in reason


def test_confirm_matches_order_rejects_garbage_amount():
    v = {"network": SOL_NETWORK, "asset": SOL_ASSET, "amount_atomic": "abc"}
    ok, reason = cc.confirm_matches_order(v, network=SOL_NETWORK, asset=SOL_ASSET, amount_usd=1.0)
    assert not ok
    assert "non-numeric" in reason


# ── coffer_client.verify_payment ─────────────────────────────────────


def test_verify_success(monkeypatch):
    monkeypatch.setenv("X402_FACILITATOR_URL", COFFER)
    with respx.mock as router:
        route = router.post(VERIFY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "verified": True,
                    "payment_id": "x402_abc",
                    "transaction": "tx1",
                    "network": SOL_NETWORK,
                    "asset": SOL_ASSET,
                    "amount_atomic": "1000000",
                },
            )
        )
        out = asyncio.run(cc.verify_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))
    assert out["verified"] is True
    assert out["amount_atomic"] == "1000000"
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["content-type"].startswith("application/json")


def test_verify_rejected_402_is_not_an_exception(monkeypatch):
    monkeypatch.setenv("X402_FACILITATOR_URL", COFFER)
    with respx.mock:
        respx.post(VERIFY_URL).mock(
            return_value=httpx.Response(402, json={"x402Version": 1, "error": "payment not found"})
        )
        out = asyncio.run(cc.verify_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))
    assert out["verified"] is False
    assert "payment not found" in out["reason"]
    assert out["http_status"] == 402


def test_verify_unreachable_fails_closed(monkeypatch):
    monkeypatch.setenv("X402_FACILITATOR_URL", COFFER)
    with respx.mock:
        respx.post(VERIFY_URL).mock(side_effect=httpx.ConnectError("conn refused"))
        with pytest.raises(cc.CofferUnavailable):
            asyncio.run(cc.verify_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))


def test_verify_unconfigured_fails_closed(monkeypatch):
    monkeypatch.delenv("X402_FACILITATOR_URL", raising=False)
    with pytest.raises(cc.CofferUnavailable, match="not configured"):
        asyncio.run(cc.verify_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))


def test_verify_retries_on_5xx_then_succeeds(monkeypatch):
    monkeypatch.setenv("X402_FACILITATOR_URL", COFFER)
    with respx.mock as router:
        route = router.post(VERIFY_URL).mock(
            side_effect=[
                httpx.Response(503, json={"error": "down"}),
                httpx.Response(200, json={"verified": True}),
            ]
        )
        out = asyncio.run(cc.verify_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))
    assert out["verified"] is True
    assert len(route.calls) == 2


def test_verify_sends_merchant_key_when_configured(monkeypatch):
    monkeypatch.setenv("X402_FACILITATOR_URL", COFFER)
    monkeypatch.setenv("X402_MERCHANT_KEY", "merchant-secret")
    with respx.mock as router:
        route = router.post(VERIFY_URL).mock(
            return_value=httpx.Response(200, json={"verified": True})
        )
        asyncio.run(cc.verify_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))
    assert route.calls.last.request.headers["authorization"] == "Bearer merchant-secret"


def test_verify_no_merchant_key_header_when_unset(monkeypatch):
    monkeypatch.setenv("X402_FACILITATOR_URL", COFFER)
    monkeypatch.delenv("X402_MERCHANT_KEY", raising=False)
    with respx.mock as router:
        route = router.post(VERIFY_URL).mock(
            return_value=httpx.Response(200, json={"verified": True})
        )
        asyncio.run(cc.verify_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))
    assert "authorization" not in route.calls.last.request.headers


def test_verify_rejects_bad_payload():
    with pytest.raises(ValueError, match="amount_usd"):
        asyncio.run(cc.verify_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 0.0))
    with pytest.raises(ValueError, match="payment_id"):
        asyncio.run(cc.verify_payment("", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))


# ── coffer_client.settle_payment ─────────────────────────────────────


def test_settle_success(monkeypatch):
    monkeypatch.setenv("X402_FACILITATOR_URL", COFFER)
    with respx.mock:
        respx.post(SETTLE_URL).mock(
            return_value=httpx.Response(200, json={"success": True, "tx_hash": "stx"})
        )
        out = asyncio.run(cc.settle_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))
    assert out["settled"] is True
    assert out["receipt"]["tx_hash"] == "stx"


def test_settle_rejected(monkeypatch):
    monkeypatch.setenv("X402_FACILITATOR_URL", COFFER)
    with respx.mock:
        respx.post(SETTLE_URL).mock(
            return_value=httpx.Response(200, json={"success": False, "error": "no auth"})
        )
        out = asyncio.run(cc.settle_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))
    assert out["settled"] is False
    assert "no auth" in out["reason"]


def test_settle_unreachable_fails_closed(monkeypatch):
    monkeypatch.setenv("X402_FACILITATOR_URL", COFFER)
    with respx.mock:
        respx.post(SETTLE_URL).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(cc.CofferUnavailable):
            asyncio.run(cc.settle_payment("x402_abc", "tx1", SOL_NETWORK, SOL_ASSET, 1.0))


# ── x402_service generate gate (coffer end-to-end) ───────────────────


@pytest.fixture
def x402_env(monkeypatch):
    """Isolate the x402 service: temp DB, sane constants, coffer URL set."""
    monkeypatch.setenv("X402_FACILITATOR_URL", COFFER)
    monkeypatch.setattr(xs, "DB_PATH", Path(tempfile.mkdtemp(prefix="wp_x402_cf_")) / "x402.db")
    monkeypatch.setattr(xs, "PRICE_PER_WALLET", 0.1)
    monkeypatch.setattr(xs, "MIN_ORDER_USD", 1.0)
    monkeypatch.setattr(xs, "FREE_WALLETS", 3)


def _paid_order(client, count=10, tx="tx123"):
    return client.post(
        "/api/v1/marketplace/generate",
        json={"chain": "sol", "count": count, "payment_tx": tx},
    )


def test_generate_paid_order_gated_on_coffer_verify(monkeypatch, x402_env):
    """A coffer-verified payment generates wallets: verify then settle (parity)."""
    from fastapi.testclient import TestClient

    with respx.mock as router:
        verify_route = router.post(VERIFY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "verified": True,
                    "payment_id": "x402_any",
                    "transaction": "tx123",
                    "network": SOL_NETWORK,
                    "asset": SOL_ASSET,
                    "amount_atomic": "1000000",  # $1.00 order
                },
            )
        )
        settle_route = router.post(SETTLE_URL).mock(
            return_value=httpx.Response(200, json={"success": True, "tx_hash": "stx"})
        )
        client = TestClient(xs.app)
        resp = _paid_order(client)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["payment_method"] == "onchain"
    assert len(body["wallets"]) == 10
    assert body["settlement"]["settled"] is True
    assert verify_route.called
    assert settle_route.called
    # Verify is the authoritative gate and runs BEFORE settlement.
    assert settle_route.calls[0].request.url.path == "/v1/x402/settle"


def test_generate_paid_order_rejected_when_coffer_rejects(monkeypatch, x402_env):
    from fastapi.testclient import TestClient

    with respx.mock as router:
        verify_route = router.post(VERIFY_URL).mock(
            return_value=httpx.Response(402, json={"error": "payment not found"})
        )
        settle_route = router.post(SETTLE_URL).mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        client = TestClient(xs.app)
        resp = _paid_order(client)

    assert resp.status_code == 402, resp.text
    assert "Payment verification failed" in resp.text
    assert verify_route.called
    assert not settle_route.called  # never settle an unverified payment


def test_generate_paid_order_fails_closed_when_coffer_unreachable(monkeypatch, x402_env):
    from fastapi.testclient import TestClient

    with respx.mock as router:
        verify_route = router.post(VERIFY_URL).mock(side_effect=httpx.ConnectError("coffer down"))
        settle_route = router.post(SETTLE_URL).mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        client = TestClient(xs.app)
        resp = _paid_order(client)

    assert resp.status_code == 402, resp.text
    assert "unavailable" in resp.text.lower()
    assert verify_route.called
    assert not settle_route.called
    # Free tier is untouched by the outage — no free wallets were consumed.
    assert xs._get_free_wallets_used("testclient") == 0


def test_generate_paid_order_confirm_match_rejects_wrong_asset(monkeypatch, x402_env):
    """Mirror check: echoed asset must match the quoted order before keys are returned."""
    from fastapi.testclient import TestClient

    with respx.mock as router:
        verify_route = router.post(VERIFY_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "verified": True,
                    "transaction": "tx123",
                    "network": SOL_NETWORK,
                    "asset": "solana:WRONGMINT",  # paid a different token
                    "amount_atomic": "1000000",
                },
            )
        )
        settle_route = router.post(SETTLE_URL).mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        client = TestClient(xs.app)
        resp = _paid_order(client)

    assert resp.status_code == 402, resp.text
    assert "asset mismatch" in resp.text
    assert verify_route.called
    assert not settle_route.called
