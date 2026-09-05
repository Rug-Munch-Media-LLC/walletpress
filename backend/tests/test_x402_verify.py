"""Tests for core/x402_verify.py — mocked facilitator client."""

from __future__ import annotations

from typing import ClassVar

import pytest

import core.x402_verify as xv


class _FakeResponse:
    def __init__(self, payload, content=b"{}"):
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class _FakeClient:
    payload: ClassVar[dict] = {}
    exc: ClassVar[Exception | None] = None

    def __init__(self):
        pass

    async def post(self, url, json=None):
        if type(self).exc is not None:
            raise type(self).exc
        return _FakeResponse(type(self).payload, content=b"x")


@pytest.fixture
def fake_client(monkeypatch):
    async def _get_client():
        return _FakeClient()

    monkeypatch.setattr(xv, "get_client", _get_client)
    _FakeClient.payload = {}
    _FakeClient.exc = None
    return _FakeClient


def test_get_supported_chains():
    chains = xv.get_supported_chains()
    assert set(chains) == {"sol", "base", "polygon", "arbitrum", "eth"}


def test_get_pay_to_known_and_unknown():
    assert xv.get_pay_to("base") == xv.CHAIN_CONFIG["base"]["pay_to"]
    assert xv.get_pay_to("nope") == xv.PAY_TO


@pytest.mark.asyncio
async def test_free_payment_short_circuits(fake_client):
    out = await xv.verify_usdc_payment("sol", "", 0)
    assert out == {"verified": True, "reason": "free", "tx_hash": "", "payer": "", "amount": 0}


@pytest.mark.asyncio
async def test_missing_tx_rejected(fake_client):
    out = await xv.verify_usdc_payment("sol", "", 5.0)
    assert out["verified"] is False
    assert "No payment tx" in out["reason"]


@pytest.mark.asyncio
async def test_unsupported_chain(fake_client):
    out = await xv.verify_usdc_payment("cardano", "tx123", 5.0)
    assert out["verified"] is False
    assert "Unsupported chain" in out["reason"]


@pytest.mark.asyncio
async def test_valid_payment(fake_client):
    _FakeClient.payload = {
        "isValid": True,
        "tx_hash": "0xdeadbeef",
        "payer": "0xpayer",
        "amount": 5.0,
    }
    out = await xv.verify_usdc_payment("base", "0xtx", 5.0)
    assert out["verified"] is True
    assert out["tx_hash"] == "0xdeadbeef"
    assert out["payer"] == "0xpayer"
    assert out["amount"] == 5.0


@pytest.mark.asyncio
async def test_invalid_payment(fake_client):
    _FakeClient.payload = {
        "isValid": False,
        "invalidReason": "already_spent",
        "invalidMessage": "dup",
    }
    out = await xv.verify_usdc_payment("sol", "sig", 1.0)
    assert out["verified"] is False
    assert "already_spent" in out["reason"]


@pytest.mark.asyncio
async def test_timeout_returns_unverified(fake_client):
    import httpx

    _FakeClient.exc = httpx.TimeoutException("timeout")
    out = await xv.verify_usdc_payment("eth", "0xtx", 2.0)
    assert out["verified"] is False
    assert "timeout" in out["reason"].lower()


@pytest.mark.asyncio
async def test_request_error_returns_error(fake_client):
    import httpx

    _FakeClient.exc = httpx.ConnectError("dns fail")
    out = await xv.verify_usdc_payment("base", "0xtx", 2.0)
    assert out["verified"] is False
    assert "dns fail" in out["reason"]
