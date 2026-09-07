"""Tests: API endpoints return correct responses.

Exercises the public FastAPI surface via an async client with httpx_mock
for external RPC calls. Follows the rugcharts/backend/tests pattern.
"""

from __future__ import annotations

import os
import re
import tempfile

os.environ["WP_VAULT_PASSWORD"] = "test-vault-password-1234567890"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_api_")
os.environ["WP_ADMIN_KEY"] = "test-admin-key-12345"
os.environ["WP_RATE_LIMIT"] = "0"

import pytest
from httpx import ASGITransport, AsyncClient

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

ADMIN_HEADERS = {"X-API-Key": "test-admin-key-12345"}
ETH_ADDRESS = "0x8b991D96E16a2232174FFACb471966ed67290D4E"


@pytest.fixture
async def client():
    """Async test client against the full FastAPI app."""
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Service metadata endpoints ──────────────────────────────────────────────


async def test_health(client):
    """GET /health returns 200 with status field."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "service" in data
    assert data["service"] == "walletpress"


async def test_version(client):
    """GET /version returns service metadata."""
    resp = await client.get("/version", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "WalletPress API"
    assert "version" in data


async def test_root(client):
    """GET / returns service + trust metadata."""
    resp = await client.get("/", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "WalletPress API"
    assert data["trust"]["open_source"] is True
    assert "docs" in data


async def test_trust_build(client):
    """GET /trust/build returns reproducible-build info."""
    resp = await client.get("/trust/build", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "WalletPress"
    assert "source_commit" in data


# ── Wallet analysis endpoints ───────────────────────────────────────────────


async def test_balance_endpoint(client, httpx_mock):
    """GET /api/v1/wallet/{address}/balance returns RPC balance."""
    httpx_mock.add_response(
        url=re.compile(r"https://eth\.llamarpc\.com"),
        json={"jsonrpc": "2.0", "id": 1, "result": "0xde0b6b3a7640000"},
        status_code=200,
    )
    resp = await client.get(
        f"/api/v1/wallet/{ETH_ADDRESS}/balance?chain=eth", headers=ADMIN_HEADERS
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["address"] == ETH_ADDRESS
    assert data["chain"] == "eth"
    assert data["balance"] == "1000000000000000000"
    assert data["token"] == "ETH"


async def test_balance_unsupported_chain(client):
    """Unsupported chain returns 400 with a clear detail."""
    resp = await client.get(
        f"/api/v1/wallet/{ETH_ADDRESS}/balance?chain=notachain", headers=ADMIN_HEADERS
    )
    assert resp.status_code == 400
    assert "chain" in resp.json()["detail"].lower()


async def test_balance_invalid_address(client):
    """Invalid address format returns 400."""
    resp = await client.get("/api/v1/wallet/notanaddress/balance?chain=eth", headers=ADMIN_HEADERS)
    assert resp.status_code == 400


async def test_verify_signature_endpoint(client):
    """POST /api/v1/wallet/verify returns verified:false for a bad signature."""
    resp = await client.post(
        "/api/v1/wallet/verify",
        params={
            "address": "11111111111111111111111111111111",
            "message": "hello",
            "signature": "abc",
            "chain": "sol",
        },
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verified"] is False
    assert data["chain"] == "sol"


async def test_verify_unsupported_chain(client):
    """Verify with an unsupported chain returns 400."""
    resp = await client.post(
        "/api/v1/wallet/verify",
        params={"address": "0xabc", "message": "hi", "signature": "abc", "chain": "bad"},
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 400


# ── Auth-protected endpoints ────────────────────────────────────────────────


async def test_write_requires_auth(client):
    """POST without an API key returns 401."""
    resp = await client.post("/api/v1/chain-vault/api-keys", json={"label": "x"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


async def test_write_with_admin_key(client):
    """POST with the admin key succeeds."""
    resp = await client.post(
        "/api/v1/chain-vault/api-keys", json={"label": "x"}, headers=ADMIN_HEADERS
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] == "x"
    assert data["api_key"].startswith("wp_")


async def test_config_endpoint(client):
    """GET /api/v1/chain-vault/config returns version + features."""
    resp = await client.get("/api/v1/chain-vault/config", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "features" in data
    assert data["features"]["api_key_auth"] is True


async def test_metrics_endpoint(client):
    """GET /metrics returns 200."""
    resp = await client.get("/metrics")
    assert resp.status_code == 200
