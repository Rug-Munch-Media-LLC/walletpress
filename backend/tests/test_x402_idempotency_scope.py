"""CWE-639: an idempotency key must not be a global handle on another's order.

Pre-fix the lookup was WHERE idempotency_key = ? with no client scope, so any
caller who guessed or observed a key received the victim's order_id.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import x402_service as xs
from core import x402_store

VICTIM = ("198.51.100.7", 5000)
OTHER = ("203.0.113.9", 5001)
ORDER = {"chain": "sol", "count": 10, "idempotency_key": "shared-key"}


@pytest.fixture
def env(monkeypatch):
    """Temp DB, cheap wallets, free tier wide enough for two 10-wallet orders."""
    db = Path(tempfile.mkdtemp(prefix="wp_x402_idem_")) / "x402.db"
    monkeypatch.setattr(xs, "DB_PATH", db)
    monkeypatch.setattr(xs, "PRICE_PER_WALLET", 0.1)
    monkeypatch.setattr(xs, "MIN_ORDER_USD", 1.0)
    monkeypatch.setattr(xs, "FREE_WALLETS", 20)
    return db


def test_same_client_replay_still_returns_the_same_order(env):
    client = TestClient(xs.app, client=VICTIM)
    first = client.post("/api/v1/marketplace/generate", json=ORDER)
    assert first.status_code == 200, first.text

    replay = client.post("/api/v1/marketplace/generate", json=ORDER)
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True
    assert replay.json()["order_id"] == first.json()["order_id"]


def test_another_client_cannot_replay_the_key(env):
    victim = TestClient(xs.app, client=VICTIM)
    first = victim.post("/api/v1/marketplace/generate", json=ORDER)
    assert first.status_code == 200, first.text
    victim_order = first.json()["order_id"]

    attacker = TestClient(xs.app, client=OTHER)
    replay = attacker.post("/api/v1/marketplace/generate", json=ORDER)

    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body.get("idempotent") is not True
    assert body["order_id"] != victim_order
    assert body["wallets"], "the attacker got their own order, not the victim's"


def test_store_lookup_is_scoped_to_the_identity(env):
    x402_store.insert_order(
        env,
        order_id="o-victim",
        chain="sol",
        count=1,
        amount_usd=0.1,
        payment_tx="",
        client_ip=VICTIM[0],
        idempotency_key="shared-key",
        client_identity="ip:198.51.100.7",
    )
    assert x402_store.find_order_by_idempotency(env, "shared-key", "ip:198.51.100.7")
    assert x402_store.find_order_by_idempotency(env, "shared-key", "ip:203.0.113.9") is None
