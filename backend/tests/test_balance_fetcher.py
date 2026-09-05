"""Tests for routers/balance_fetcher.py — mocked httpx, no network."""

from __future__ import annotations

from typing import ClassVar

import pytest

import routers.balance_fetcher as bf


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient in balance_fetcher."""

    payload: ClassVar[dict] = {}
    exc: ClassVar[Exception | None] = None
    last_call: ClassVar[tuple | None] = None

    def __init__(self, timeout=8):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        type(self).last_call = ("POST", url, json)
        if type(self).exc is not None:
            raise type(self).exc
        return _FakeResponse(type(self).payload)

    async def get(self, url):
        type(self).last_call = ("GET", url, None)
        if type(self).exc is not None:
            raise type(self).exc
        return _FakeResponse(type(self).payload)


@pytest.fixture
def fake_http(monkeypatch):
    monkeypatch.setattr(bf.httpx, "AsyncClient", _FakeClient)
    _FakeClient.payload = {}
    _FakeClient.exc = None
    _FakeClient.last_call = None
    return _FakeClient


@pytest.mark.asyncio
async def test_evm_balance_success(fake_http):
    fake_http.payload = {"result": hex(10**18)}
    out = await bf.fetch_balance("eth", "0xabc")
    assert out["balance"] == str(10**18)
    assert out["balance_decimal"] == 1.0
    assert out["source"] == "rpc:eth"


@pytest.mark.asyncio
async def test_evm_balance_failure_returns_zero(fake_http):
    fake_http.exc = ConnectionError("rpc down")
    out = await bf.fetch_balance("eth", "0xabc")
    assert out["balance"] == "0"
    assert out["source"] == "rpc:eth"


@pytest.mark.asyncio
async def test_solana_balance_success(fake_http):
    fake_http.payload = {"result": {"value": 2 * 10**9}}
    out = await bf.fetch_balance("sol", "SolAddr")
    assert out["balance_decimal"] == 2.0


@pytest.mark.asyncio
async def test_tron_balance_success(fake_http):
    fake_http.payload = {"data": [{"balance": 5 * 10**6}]}
    out = await bf.fetch_balance("trx", "TAddr")
    assert out["balance_decimal"] == 5.0


@pytest.mark.asyncio
async def test_btc_balance_success(fake_http):
    fake_http.payload = {"1Addr": {"final_balance": 10**8}}
    out = await bf.fetch_balance("btc", "1Addr")
    assert out["balance_decimal"] == 1.0
    assert out["source"] == "blockchain.info"


@pytest.mark.asyncio
async def test_blockchair_balance_success(fake_http):
    fake_http.payload = {"data": {"DAddr": {"address": {"balance": 10**8}}}}
    out = await bf.fetch_balance("doge", "DAddr")
    assert out["balance_decimal"] == 1.0
    assert out["source"] == "blockchair"


@pytest.mark.asyncio
async def test_cosmos_balance_success(fake_http):
    fake_http.payload = {"balance": {"amount": "3000000"}}
    out = await bf.fetch_balance("atom", "cosmos1addr")
    assert out["balance_decimal"] == 3.0


@pytest.mark.asyncio
async def test_algorand_balance_success(fake_http):
    fake_http.payload = {"amount": 2 * 10**6}
    out = await bf.fetch_balance("algo", "ALGOADDR")
    assert out["balance_decimal"] == 2.0


@pytest.mark.asyncio
async def test_stellar_balance_success(fake_http):
    fake_http.payload = {"balances": [{"asset_type": "native", "balance": "10.5"}]}
    out = await bf.fetch_balance("xlm", "GADDR")
    assert out["balance_decimal"] == 10.5


@pytest.mark.asyncio
async def test_filecoin_balance_success(fake_http):
    fake_http.payload = {"result": hex(10**18)}
    out = await bf.fetch_balance("fil", "f1addr")
    assert out["balance_decimal"] == 1.0


@pytest.mark.asyncio
async def test_ripple_balance_success(fake_http):
    fake_http.payload = {"result": {"status": "success", "account_data": {"Balance": "3000000"}}}
    out = await bf.fetch_balance("xrp", "rADDR")
    assert out["balance_decimal"] == 3.0


@pytest.mark.asyncio
async def test_cardano_balance_success(fake_http):
    fake_http.payload = {"totalBalance": 4 * 10**6}
    out = await bf.fetch_balance("ada", "addr1")
    assert out["balance_decimal"] == 4.0


@pytest.mark.asyncio
async def test_unsupported_chain(fake_http):
    out = await bf.fetch_balance("madeupchain", "addr")
    assert out["source"] == "unsupported"
    assert "No balance API" in out["error"]


@pytest.mark.asyncio
async def test_substrate_unknown_chain(fake_http, monkeypatch):
    # force a chain into the substrate branch with no subscan mapping
    monkeypatch.setitem(bf.EVM_RPC, "dot", None) if False else None
    out = await bf._substrate_balance("unknown", "addr")
    assert out["source"] == "unsupported"
