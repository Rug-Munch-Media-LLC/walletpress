"""Tests for core/x402_marketplace.py — pure helpers, sqlite _DB, and router endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.x402_marketplace as mp
from core.x402_marketplace import _DB, calc_price

# ── calc_price ────────────────────────────────────────────────────


def test_calc_price_tiers():
    assert calc_price(1) == 0.01
    assert calc_price(100) == 1.0
    assert calc_price(1000) == 5.0
    assert calc_price(10000) == 20.0
    assert calc_price(100000) == 100.0


# ── _DB (sqlite) ──────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    return _DB(tmp_path / "mkt.db")


def test_db_credits_roundtrip(db):
    assert db.get_balance("k1") == 0.0
    db.add_credits("k1", 10.0)
    db.add_credits("k1", 5.0)
    assert db.get_balance("k1") == 15.0
    assert db.deduct("k1", 4.0) is True
    assert db.get_balance("k1") == 11.0


def test_db_deduct_insufficient(db):
    db.add_credits("k2", 1.0)
    assert db.deduct("k2", 5.0) is False
    assert db.deduct("missing", 1.0) is False
    assert db.get_balance("k2") == 1.0


def test_db_log_order(db):
    db.log_order("o1", "sol", 10, 0.1, "", "1.2.3.4", "idem-1")
    conn = db._conn()
    row = conn.execute("SELECT * FROM orders WHERE order_id = 'o1'").fetchone()
    conn.close()
    assert row["chain"] == "sol"
    assert row["payment_tx"] == "free"
    assert row["idempotency_key"] == "idem-1"


# ── payment verification helper ───────────────────────────────────


@pytest.mark.asyncio
async def test_verify_onchain_payment_free(monkeypatch):
    assert await mp._verify_onchain_payment("sol", "", 0) is True


@pytest.mark.asyncio
async def test_verify_onchain_payment_no_tx(monkeypatch):
    assert await mp._verify_onchain_payment("sol", "", 5) is False


@pytest.mark.asyncio
async def test_verify_onchain_payment_delegates(monkeypatch):
    async def fake_verify(chain, tx, expected):
        return {"verified": True}

    monkeypatch.setattr("core.x402_verify.verify_usdc_payment", fake_verify)
    assert await mp._verify_onchain_payment("sol", "tx", 5) is True


# ── warm pool ─────────────────────────────────────────────────────


def test_pull_from_warm_pool():
    mp._WARM_POOL.clear()
    mp._WARM_POOL["sol"] = [{"address": f"a{i}"} for i in range(5)]
    taken = mp._pull_from_warm_pool("sol", 3)
    assert len(taken) == 3
    assert len(mp._WARM_POOL["sol"]) == 2
    assert mp._pull_from_warm_pool("sol", 10) == []


# ── router endpoints ──────────────────────────────────────────────


@pytest.fixture
def api():

    app = FastAPI()
    app.include_router(mp.router)
    return TestClient(app)


def test_pricing_endpoint(api):
    r = api.get("/api/v1/marketplace/pricing")
    assert r.status_code == 200
    body = r.json()
    assert body["pricing"]["minimum_order_usd"] == 1.0
    assert len(body["pricing"]["tiers"]) == 4


def test_balance_endpoint_empty_key(api):
    r = api.get("/api/v1/marketplace/balance")
    assert r.status_code == 200
    assert "error" in r.json()


def test_buy_credits_requires_payment(api):
    r = api.post("/api/v1/marketplace/credits", json={"amount": 10, "payment_tx": ""})
    assert r.status_code == 402


def test_buy_credits_success_and_balance(api):
    r = api.post("/api/v1/marketplace/credits", json={"amount": 25, "payment_tx": "sig"})
    assert r.status_code == 200
    key = r.json()["api_key"]
    r2 = api.get(f"/api/v1/marketplace/balance?api_key={key}")
    assert r2.json()["balance"] == 25.0
    assert r2.json()["can_generate"] == 2500


def test_generate_unsupported_chain(api):
    r = api.post("/api/v1/marketplace/generate", json={"chain": "cardano", "count": 1})
    assert r.status_code == 400


def test_generate_payment_required_for_large_order(api):
    r = api.post("/api/v1/marketplace/generate", json={"chain": "sol", "count": 100})
    assert r.status_code == 402
    detail = r.json()["detail"]
    assert detail["error"] == "Payment required"
    assert detail["amount_usd"] == 1.0


def test_generate_insufficient_credits(api):
    r = api.post(
        "/api/v1/marketplace/generate",
        json={"chain": "sol", "count": 100, "api_key": "no_such_key"},
    )
    assert r.status_code == 402
    assert r.json()["detail"]["error"] == "Insufficient credits"


def test_generate_idempotent_replay(api):
    db = mp.get_db()
    db.log_order("o9", "sol", 5, 0.05, "free", "", "idem-9")
    r = api.post(
        "/api/v1/marketplace/generate",
        json={"chain": "sol", "count": 5, "idempotency_key": "idem-9"},
    )
    assert r.status_code == 200
    assert r.json()["idempotent"] is True
    assert r.json()["order_id"] == "o9"


def test_generate_async_unsupported_chain(api):
    r = api.post("/api/v1/marketplace/generate/async", json={"chain": "cardano", "count": 1})
    assert r.status_code == 400


def test_get_job_not_found(api):
    r = api.get("/api/v1/marketplace/jobs/job_missing")
    assert r.status_code == 404


def test_verify_receipt_not_found(api):
    r = api.get("/api/v1/marketplace/verify-receipt?order_id=nope")
    assert r.status_code == 404


def test_warm_pool_status(api):
    r = api.get("/api/v1/marketplace/warm-pool/status")
    assert r.status_code == 200
    assert r.json()["target_per_chain"] == mp._WARM_POOL_TARGET


def test_webhook_set_get_delete(api):
    r = api.post(
        "/api/v1/marketplace/webhooks",
        json={"api_key": "wp_cred_abc", "url": "https://example.com/hook"},
    )
    assert r.status_code == 200
    assert r.json()["webhook_set"] is True
    r2 = api.get("/api/v1/marketplace/webhooks?api_key=wp_cred_abc")
    assert r2.json()["webhook_url"] == "https://example.com/hook"
    r3 = api.request("DELETE", "/api/v1/marketplace/webhooks?api_key=wp_cred_abc")
    assert r3.json()["deleted"] is True


def test_webhook_rejects_http(api):
    r = api.post(
        "/api/v1/marketplace/webhooks",
        json={"api_key": "k", "url": "http://example.com/hook"},
    )
    assert r.status_code == 400


def test_multi_sig_validation(api):
    r = api.post(
        "/api/v1/marketplace/multi-sig",
        json={"chain": "eth", "required": 5, "total_keys": 3},
    )
    assert r.status_code == 400


def test_multi_sig_with_provided_keys(api):
    keys = ["04" + "ab" * 32, "04" + "cd" * 32, "04" + "ef" * 32]
    r = api.post(
        "/api/v1/marketplace/multi-sig",
        json={"chain": "eth", "required": 2, "total_keys": 3, "public_keys": keys},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["multi_sig"] is True
    assert body["address"].startswith("0x")
    assert len(body["public_keys"]) == 3


# ── async job worker ──────────────────────────────────────────────


class _FakeWallet:
    address = "0xfake"
    private_key_hex = "aa" * 32
    mnemonic = "test mnemonic"
    derivation_path = "m/44'/60'/0'/0/0"


def test_run_async_job_success(monkeypatch):
    monkeypatch.setattr(
        mp,
        "get_generator",
        lambda: type("G", (), {"generate": staticmethod(lambda **kw: _FakeWallet())})(),
    )
    mp._jobs.clear()
    mp._run_async_job("job_ok", "sol", 2, "order_x", "", "")
    job = mp._jobs["job_ok"]
    assert job["status"] == "completed"
    assert len(job["wallets"]) == 2


def test_run_async_job_failure(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("gen failed")

    monkeypatch.setattr(
        mp, "get_generator", lambda: type("G", (), {"generate": staticmethod(boom)})()
    )
    mp._run_async_job("job_bad", "sol", 1, "order_y", "", "")
    assert mp._jobs["job_bad"]["status"] == "failed"
    assert "gen failed" in mp._jobs["job_bad"]["error"]


def test_generate_async_free_tier(api, monkeypatch):
    monkeypatch.setattr(
        mp,
        "get_generator",
        lambda: type("G", (), {"generate": staticmethod(lambda **kw: _FakeWallet())})(),
    )
    r = api.post("/api/v1/marketplace/generate/async", json={"chain": "sol", "count": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert body["payment_method"] == "free"
    job = api.get(f"/api/v1/marketplace/jobs/{body['job_id']}")
    assert job.status_code == 200
