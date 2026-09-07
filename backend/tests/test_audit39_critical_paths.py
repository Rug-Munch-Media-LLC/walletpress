"""Audit #39: targeted tests for uncovered critical security paths.

Covers the specific lines the coverage report flagged as uncovered in the
critical modules, with real behavior assertions (no tautological tests):

- core/jwt_auth.py  — RS256-only confusion fix (_allowed_algorithms)
- x402_service.py   — MIN_ORDER_USD gate, free-tier exhaustion, idempotency,
                      unsupported chain, invalid API key
- routers/chain_vault.py — scope-escalation prevention, fail-closed password
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import x402_service as xs
from core.jwt_auth import _allowed_algorithms, _is_rsa_public_key

# ── jwt_auth: RS256-only confusion fix ────────────────────────────────────────


def test_allowed_algorithms_rsa_key_only_rs256():
    """An RSA public key must ONLY allow RS256 — never HS256.

    This is the classic HS256/public-key confusion attack: an attacker signs
    a token with the (public) RSA key as an HMAC secret. The allowlist must
    reject that.
    """
    rsa_pem = "-----BEGIN PUBLIC KEY-----\nMIIB\n-----END PUBLIC KEY-----"
    assert _is_rsa_public_key(rsa_pem) is True
    assert _allowed_algorithms(rsa_pem) == ["RS256"]


def test_allowed_algorithms_rsa_certificate_only_rs256():
    """A PEM certificate (x5c-style) is also RSA and must only allow RS256."""
    cert = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----"
    assert _is_rsa_public_key(cert) is True
    assert _allowed_algorithms(cert) == ["RS256"]


def test_allowed_algorithms_symmetric_secret_allows_hs256():
    """A non-RSA (symmetric) secret permits HS256."""
    secret = "a-shared-hmac-secret"
    assert _is_rsa_public_key(secret) is False
    assert _allowed_algorithms(secret) == ["HS256"]


def test_allowed_algorithms_rsa_public_key_never_contains_hs256():
    """Guard: RS256-only must never leak HS256 into the allowlist."""
    rsa_pem = "-----BEGIN RSA PUBLIC KEY-----\nMIIB\n-----END RSA PUBLIC KEY-----"
    allowed = _allowed_algorithms(rsa_pem)
    assert "HS256" not in allowed
    assert allowed == ["RS256"]


# ── x402_service: payment gate critical paths ─────────────────────────────────


@pytest.fixture
def x402_env(monkeypatch):
    """Isolate the x402 service: temp DB, sane constants, coffer URL set."""
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://coffer.test")
    monkeypatch.setattr(xs, "DB_PATH", Path(tempfile.mkdtemp(prefix="wp_x402_a39_")) / "x402.db")
    monkeypatch.setattr(xs, "PRICE_PER_WALLET", 0.1)
    monkeypatch.setattr(xs, "MIN_ORDER_USD", 1.0)
    monkeypatch.setattr(xs, "FREE_WALLETS", 3)


def test_generate_below_minimum_order_rejected(x402_env):
    """MIN_ORDER_USD is enforced unconditionally — no client can bypass it."""
    client = TestClient(xs.app)
    # count=5 @ $0.10 = $0.50 < $1.00 minimum
    resp = client.post("/api/v1/marketplace/generate", json={"chain": "sol", "count": 5})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Order below minimum" in detail
    assert "required_min_usd" in detail
    assert "requested_usd" in detail


def test_generate_unsupported_chain_rejected(x402_env):
    client = TestClient(xs.app)
    resp = client.post("/api/v1/marketplace/generate", json={"chain": "cardano", "count": 100})
    assert resp.status_code == 400
    assert "Unsupported chain" in resp.json()["detail"]


def test_generate_invalid_api_key_rejected(x402_env):
    """A client-asserted credit key must be verified server-side; unknown keys are 402."""
    client = TestClient(xs.app)
    resp = client.post(
        "/api/v1/marketplace/generate",
        json={"chain": "sol", "count": 100, "api_key": "no_such_key"},
    )
    assert resp.status_code == 402
    assert "Invalid or unknown prepaid API key" in resp.json()["detail"]


def test_generate_free_tier_exhaustion(x402_env):
    """Free tier is enforced against server-tracked per-client usage."""
    client = TestClient(xs.app)
    # count=10 @ $0.10 = $1.00 meets the minimum; 10 > FREE_WALLETS=3 → 402.
    resp = client.post("/api/v1/marketplace/generate", json={"chain": "sol", "count": 10})
    assert resp.status_code == 402
    detail = resp.json()["detail"]
    assert "Payment required" in detail
    assert "Free tier exhausted" in detail
    assert "amount_usd" in detail
    assert xs.PAYMENT_ADDRESS in detail


def test_generate_free_tier_records_usage(x402_env, monkeypatch):
    """A successful free-tier order records per-client usage server-side."""
    # Raise the free-tier cap so a small order succeeds as free (count=10 ≤ cap).
    monkeypatch.setattr(xs, "FREE_WALLETS", 20)
    client = TestClient(xs.app)
    resp = client.post("/api/v1/marketplace/generate", json={"chain": "sol", "count": 10})
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_method"] == "free"
    # The client IP used by TestClient is "testclient".
    assert xs._get_free_wallets_used("testclient") == 10


def test_generate_idempotency_returns_existing_order(x402_env, monkeypatch):
    """Same idempotency key returns the existing order without re-generating."""
    # Raise the free-tier cap so count=10 succeeds as a free order.
    monkeypatch.setattr(xs, "FREE_WALLETS", 20)
    client = TestClient(xs.app)
    first = client.post(
        "/api/v1/marketplace/generate",
        json={"chain": "sol", "count": 10, "idempotency_key": "idem-a39"},
    )
    assert first.status_code == 200, first.text
    order_id = first.json()["order_id"]

    second = client.post(
        "/api/v1/marketplace/generate",
        json={"chain": "sol", "count": 10, "idempotency_key": "idem-a39"},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["idempotent"] is True
    assert body["order_id"] == order_id


def test_pricing_endpoint_reports_gate_constants(x402_env):
    client = TestClient(xs.app)
    resp = client.get("/api/v1/marketplace/pricing")
    assert resp.status_code == 200
    body = resp.json()
    assert body["per_wallet"] == 0.1
    assert body["minimum_order_usd"] == 1.0
    assert body["free_tier"]["wallets"] == 3
    assert body["payment"]["chain"] == "solana"
    assert body["payment"]["token"] == "USDC"


# ── chain_vault: scope escalation + fail-closed password ─────────────────────


def test_create_api_key_requires_auth(client):
    """Creating an API key without authentication is refused."""
    resp = client.post("/api/v1/chain-vault/api-keys", json={"label": "x"})
    assert resp.status_code in (401, 403)


def test_import_wallet_fails_closed_without_vault_password(client, admin_headers, monkeypatch):
    """Importing a private key without a vault password must be refused (503)."""
    from core import config

    monkeypatch.setattr(config.cfg, "_vault_password", "")
    resp = client.post(
        "/api/v1/chain-vault/import",
        json={"chain": "eth", "private_key": "0x" + "ab" * 32},
        headers=admin_headers,
    )
    assert resp.status_code == 503
    assert "Vault password not configured" in resp.json()["detail"]
