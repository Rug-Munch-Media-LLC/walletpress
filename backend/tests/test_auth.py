"""Tests: auth middleware and API key authentication.

Covers the KeyStore (persistent API key store), the role hierarchy, and the
`require_auth_on_mutations` middleware that guards write endpoints.

Pattern follows rugcharts/backend/tests: pytest + httpx_mock, async fixtures.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-vault-password-1234567890"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_auth_")
os.environ["WP_ADMIN_KEY"] = "test-admin-key-12345"
os.environ["WP_RATE_LIMIT"] = "0"

import pytest
from httpx import ASGITransport, AsyncClient

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from core.auth import ROLE_HIERARCHY, KeyStore, role_has_at_least

ADMIN_HEADERS = {"X-API-Key": "test-admin-key-12345"}


@pytest.fixture
def key_store() -> KeyStore:
    """A fresh on-disk KeyStore for each test."""
    return KeyStore(Path(tempfile.mkstemp(suffix=".json")[1]))


@pytest.fixture
async def client():
    """Async test client against the full FastAPI app."""
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Role hierarchy ──────────────────────────────────────────────────────────


def test_role_hierarchy():
    """Role hierarchy: admin > operator > viewer."""
    assert ROLE_HIERARCHY["admin"] == 3
    assert ROLE_HIERARCHY["operator"] == 2
    assert ROLE_HIERARCHY["viewer"] == 1


def test_role_has_at_least():
    """role_has_at_least() enforces the hierarchy."""
    assert role_has_at_least("admin", "admin") is True
    assert role_has_at_least("admin", "viewer") is True
    assert role_has_at_least("operator", "admin") is False
    assert role_has_at_least("viewer", "admin") is False
    assert role_has_at_least("unknown", "viewer") is False


# ── KeyStore ────────────────────────────────────────────────────────────────


def test_create_key(key_store):
    """create() returns a key_id and raw_key with wp_ prefix."""
    key_id, raw_key = key_store.create(label="test", scopes=["wallet.read"])
    assert key_id.startswith("wp_")
    assert raw_key.startswith("wp_")
    assert len(key_id) > 8
    assert len(raw_key) > 8


def test_verify_valid_key(key_store):
    """verify() returns the APIKey for a valid raw key."""
    _, raw_key = key_store.create(label="verify-me", scopes=["wallet.read"])
    result = key_store.verify(raw_key)
    assert result is not None
    assert result.label == "verify-me"
    assert "wallet.read" in result.scopes


def test_verify_wrong_key(key_store):
    """verify() returns None for an unknown key."""
    key_store.create(label="a", scopes=["wallet.read"])
    assert key_store.verify("wp_wrong_key_that_does_not_exist") is None


def test_verify_revoked_key(key_store):
    """verify() returns None for a revoked key."""
    key_id, raw_key = key_store.create(label="revoke-me", scopes=["wallet.read"])
    assert key_store.verify(raw_key) is not None
    key_store.revoke(key_id)
    assert key_store.verify(raw_key) is None


def test_create_invalid_role(key_store):
    """create() rejects roles outside the hierarchy."""
    with pytest.raises(ValueError, match="Invalid role"):
        key_store.create(label="bad", scopes=["wallet.read"], role="superadmin")


def test_key_store_persistence():
    """Keys survive a KeyStore reload from the same path."""
    path = Path(tempfile.mkstemp(suffix=".json")[1])
    ks1 = KeyStore(path)
    _, raw_key = ks1.create(label="persist", scopes=["wallet.read"])
    ks2 = KeyStore(path)
    assert ks2.verify(raw_key) is not None


# ── Auth middleware (require_auth_on_mutations) ─────────────────────────────


async def test_write_without_key_returns_401(client):
    """POST without an API key is rejected with 401."""
    resp = await client.post("/api/v1/chain-vault/api-keys", json={"label": "x"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


async def test_write_with_invalid_key_returns_403(client):
    """POST with an invalid API key is rejected with 403."""
    resp = await client.post(
        "/api/v1/chain-vault/api-keys",
        json={"label": "x"},
        headers={"X-API-Key": "wp_invalid_key"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


async def test_write_with_admin_key_succeeds(client):
    """POST with the admin key (implicit admin role) succeeds."""
    resp = await client.post(
        "/api/v1/chain-vault/api-keys", json={"label": "x"}, headers=ADMIN_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["api_key"].startswith("wp_")


async def test_read_without_key_allowed(client):
    """GET on a non-team path is allowed without a key."""
    resp = await client.get("/api/v1/chain-vault/config")
    assert resp.status_code == 200


async def test_health_is_public(client):
    """Health endpoint is exempt from auth."""
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_team_keys_require_admin(client):
    """GET /api/v1/team/keys requires an authenticated admin caller."""
    # No key -> 401 (team paths always need auth)
    resp = await client.get("/api/v1/team/keys")
    assert resp.status_code == 401
