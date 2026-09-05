"""Tests for routers/health_monitor.py — mocked vault, no network."""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.health_monitor as hm


class _FakeWallet:
    def __init__(
        self, wid="w1", created_at=None, balance_usd=100.0, encrypted=True, encrypted_key="k"
    ):
        self.id = wid
        self.address = "0xaddr"
        self.chain = "eth"
        self.created_at = created_at if created_at is not None else time.time()
        self.balance_usd = balance_usd
        self.encrypted = encrypted
        self.encrypted_key = encrypted_key


class _FakeVault:
    def __init__(self, wallets=None):
        self._wallets = {w.id: w for w in (wallets or [])}

    def get(self, wallet_id):
        return self._wallets.get(wallet_id)

    def get_rotations(self, wallet_id):
        return []

    def list(self, limit=10000):
        return list(self._wallets.values())


@pytest.fixture
def api(monkeypatch):
    vault = _FakeVault([_FakeWallet("w1")])
    monkeypatch.setattr(hm, "get_vault", lambda: vault)
    app = FastAPI()
    app.include_router(hm.router)
    return TestClient(app)


@pytest.fixture
def fresh_db(monkeypatch):
    monkeypatch.setattr(hm, "_monitor_db", None)
    monkeypatch.setattr(hm, "_health_cache", {})
    yield
    # connection was created inside the app's worker thread; just drop the ref
    hm._monitor_db = None


def test_check_wallet_health(api, fresh_db):
    r = api.post("/api/v1/health/check/w1")
    assert r.status_code == 200
    body = r.json()
    assert body["wallet_id"] == "w1"
    assert 0 <= body["health"]["score"] <= 100
    assert body["status"] in {"healthy", "needs_attention", "critical"}


def test_check_unknown_wallet_404(api, fresh_db):
    r = api.post("/api/v1/health/check/missing")
    assert r.status_code == 404


def test_health_history(api, fresh_db):
    api.post("/api/v1/health/check/w1")
    r = api.get("/api/v1/health/check/w1/history")
    assert r.status_code == 200
    assert len(r.json()["history"]) >= 1


def test_dashboard_empty_vault(monkeypatch):
    monkeypatch.setattr(hm, "get_vault", lambda: _FakeVault([]))
    app = FastAPI()
    app.include_router(hm.router)
    client = TestClient(app)
    r = client.get("/api/v1/health/dashboard")
    assert r.status_code == 200
    assert r.json()["total_wallets"] == 0


def test_dashboard_with_wallet(api, fresh_db):
    r = api.get("/api/v1/health/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["total_wallets"] == 1
    assert body["wallets"][0]["wallet_id"] == "w1"


def test_alerts_below_threshold(monkeypatch, fresh_db):
    sick = _FakeWallet("sick", balance_usd=0, encrypted=False, encrypted_key="")
    monkeypatch.setattr(hm, "get_vault", lambda: _FakeVault([sick]))
    app = FastAPI()
    app.include_router(hm.router)
    client = TestClient(app)
    r = client.get("/api/v1/health/alerts?threshold=71")
    assert r.status_code == 200
    body = r.json()
    assert body["threshold"] == 71
    assert body["total"] == 1
    assert body["alerts"][0]["wallet_id"] == "sick"


def test_cached_health_reuses_cache(monkeypatch):
    monkeypatch.setattr(hm, "get_vault", lambda: _FakeVault([_FakeWallet("w1")]))
    monkeypatch.setattr(hm, "_health_cache", {})
    first = hm._cached_health("w1")
    second = hm._cached_health("w1")
    assert first is second


def test_compute_health_red_flags(monkeypatch):
    old_wallet = _FakeWallet(
        "old",
        created_at=time.time() - 400 * 86400,
        balance_usd=0,
        encrypted=False,
        encrypted_key="",
    )
    monkeypatch.setattr(hm, "get_vault", lambda: _FakeVault([old_wallet]))
    result = hm._compute_health("old")
    assert result["score"] < 80
    assert "Zero balance" in " ".join(result["red_flags"])
    assert result["encrypted"] is False
