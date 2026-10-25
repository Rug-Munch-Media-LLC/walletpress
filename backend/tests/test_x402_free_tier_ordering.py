"""Fail-closed ordering: quota is reserved before keys exist, and refunded.

Two properties the pre-fix gate got wrong: usage was recorded only after the
wallets were written (so a crash lost the debit), and a reservation that later
failed could not be taken back.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import x402_service as xs
from core import x402_store

CLIENT = ("198.51.100.7", 5000)
ORDER = {"chain": "sol", "count": 10}


@pytest.fixture
def env(monkeypatch):
    db = Path(tempfile.mkdtemp(prefix="wp_x402_order_")) / "x402.db"
    monkeypatch.setattr(xs, "DB_PATH", db)
    monkeypatch.setattr(xs, "PRICE_PER_WALLET", 0.1)
    monkeypatch.setattr(xs, "MIN_ORDER_USD", 1.0)
    monkeypatch.setattr(xs, "FREE_WALLETS", 20)
    return db


def test_quota_is_reserved_before_any_wallet_is_generated(env, monkeypatch):
    """At generation time the debit is already committed, not pending."""
    observed: dict[str, int] = {}
    real = xs._generate_wallets

    def spy(chain, count, order_id):
        observed["used"] = x402_store.free_wallets_used(env, CLIENT[0])
        return real(chain, count, order_id)

    monkeypatch.setattr(xs, "_generate_wallets", spy)
    resp = TestClient(xs.app, client=CLIENT).post("/api/v1/marketplace/generate", json=ORDER)

    assert resp.status_code == 200, resp.text
    assert observed["used"] == 10, "quota was not reserved before generation"
    assert x402_store.free_wallets_used(env, CLIENT[0]) == 10, "post-write double count"


def test_a_failed_order_releases_its_reservation(env, monkeypatch):
    """Generation failure must not burn the client's free tier."""
    real = xs._generate_wallets

    def boom(chain, count, order_id):
        raise RuntimeError("generator exploded")

    monkeypatch.setattr(xs, "_generate_wallets", boom)
    client = TestClient(xs.app, client=CLIENT, raise_server_exceptions=False)
    resp = client.post("/api/v1/marketplace/generate", json=ORDER)

    assert resp.status_code == 500
    assert x402_store.free_wallets_used(env, CLIENT[0]) == 0

    # And the same client can retry for the full quota.
    monkeypatch.setattr(xs, "_generate_wallets", real)
    retry = TestClient(xs.app, client=CLIENT).post(
        "/api/v1/marketplace/generate", json=ORDER
    )
    assert retry.status_code == 200, retry.text
