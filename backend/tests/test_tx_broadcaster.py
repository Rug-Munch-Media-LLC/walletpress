"""Tests for routers/tx_broadcaster.py — mocked httpx, no network."""

from __future__ import annotations

from typing import ClassVar

import pytest

import routers.tx_broadcaster as tb


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient in tx_broadcaster."""

    payload: ClassVar[dict] = {}
    exc: ClassVar[Exception | None] = None
    last_post: ClassVar[tuple | None] = None

    def __init__(self, timeout=15):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        type(self).last_post = (url, json)
        if type(self).exc is not None:
            raise type(self).exc
        return _FakeResponse(type(self).payload)


@pytest.fixture
def fake_http(monkeypatch):
    monkeypatch.setattr(tb_http(), "AsyncClient", _FakeClient)
    _FakeClient.payload = {}
    _FakeClient.exc = None
    _FakeClient.last_post = None
    return _FakeClient


def tb_http():
    import httpx

    return httpx


@pytest.mark.asyncio
async def test_evm_broadcast_success(fake_http):
    fake_http.payload = {"result": "0xabc123"}
    out = await tb.broadcast("eth", "0xsigned")
    assert out == {"broadcast": True, "tx_hash": "0xabc123", "chain": "eth"}
    _url, body = fake_http.last_post
    assert body["method"] == "eth_sendRawTransaction"
    assert body["params"] == ["0xsigned"]


@pytest.mark.asyncio
async def test_evm_broadcast_rpc_error(fake_http):
    fake_http.payload = {"error": {"message": "intrinsic gas too low"}}
    out = await tb.broadcast("ETH", "0xsigned")
    assert out["broadcast"] is False
    assert "intrinsic gas" in out["error"]


@pytest.mark.asyncio
async def test_solana_broadcast_success(fake_http):
    fake_http.payload = {"result": "sig123"}
    out = await tb.broadcast("sol", "b64tx")
    assert out == {"broadcast": True, "tx_hash": "sig123", "chain": "sol"}
    _url, body = fake_http.last_post
    assert body["method"] == "sendTransaction"


@pytest.mark.asyncio
async def test_tron_broadcast_success(fake_http):
    fake_http.payload = {"result": True, "txid": "trxhash"}
    out = await tb.broadcast("trx", "rawtx")
    assert out == {"broadcast": True, "tx_hash": "trxhash", "chain": "trx"}


@pytest.mark.asyncio
async def test_tron_broadcast_failure(fake_http):
    fake_http.payload = {"result": False, "Error": "bad tx"}
    out = await tb.broadcast("trx", "rawtx")
    assert out == {"broadcast": False, "error": "bad tx"}


@pytest.mark.asyncio
async def test_btc_family_broadcast_success(fake_http):
    fake_http.payload = {"data": {"transaction_hash": "btc_hash"}}
    out = await tb.broadcast("doge", "rawhex")
    assert out == {"broadcast": True, "tx_hash": "btc_hash", "chain": "doge"}
    url, _ = fake_http.last_post
    assert "dogecoin" in url


@pytest.mark.asyncio
async def test_unsupported_chain(fake_http):
    out = await tb.broadcast("cardano", "tx")
    assert out["broadcast"] is False
    assert "No broadcast support" in out["error"]


@pytest.mark.asyncio
async def test_network_exception_returns_error(fake_http):
    fake_http.exc = ConnectionError("boom")
    out = await tb.broadcast("eth", "0xsigned")
    assert out["broadcast"] is False
    assert "boom" in out["error"]
