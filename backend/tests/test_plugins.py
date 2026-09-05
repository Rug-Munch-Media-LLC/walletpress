"""Tests for plugins/sdk.py, plugins/__init__.py, and plugins/defi.py."""

from __future__ import annotations

import pytest

import plugins
from plugins import defi
from plugins.sdk import (
    WalletPressPlugin,
    execute_plugin_tool,
    get_all_tools,
    get_plugin,
    list_plugins,
    register_plugin,
)

# ── sdk registry ──────────────────────────────────────────────────


class _Dummy(WalletPressPlugin):
    name = "dummy_test"
    description = "test plugin"

    def tools(self):
        return [{"name": "dummy_tool", "description": "d", "parameters": {}}]

    async def execute(self, tool, params):
        return {"ok": True, "tool": tool}


@pytest.fixture
def dummy():
    plugin = _Dummy()
    register_plugin(plugin)
    yield plugin
    plugins.sdk._plugins.pop("dummy_test", None)


def test_register_and_get(dummy):
    assert get_plugin("dummy_test") is dummy
    assert get_plugin("missing") is None


def test_register_requires_name():
    class NoName(WalletPressPlugin):
        pass

    with pytest.raises(ValueError, match="name"):
        register_plugin(NoName())


def test_list_plugins_includes_dummy(dummy):
    names = [p["name"] for p in list_plugins()]
    assert "dummy_test" in names
    entry = next(p for p in list_plugins() if p["name"] == "dummy_test")
    assert entry["tools"] == ["dummy_tool"]
    assert entry["version"] == "1.0.0"


def test_get_all_tools(dummy):
    tools = get_all_tools()
    assert any(t["name"] == "dummy_tool" for t in tools)


@pytest.mark.asyncio
async def test_execute_plugin_tool(dummy):
    out = await execute_plugin_tool("dummy_test", "dummy_tool", {})
    assert out == {"ok": True, "tool": "dummy_tool"}


@pytest.mark.asyncio
async def test_execute_plugin_tool_not_found():
    out = await execute_plugin_tool("nope", "t", {})
    assert "not found" in out["error"]


@pytest.mark.asyncio
async def test_execute_plugin_tool_not_implemented():
    class Empty(WalletPressPlugin):
        name = "empty_test"

    register_plugin(Empty())
    try:
        out = await execute_plugin_tool("empty_test", "t", {})
        assert "not implemented" in out["error"]
    finally:
        plugins.sdk._plugins.pop("empty_test", None)


@pytest.mark.asyncio
async def test_execute_plugin_tool_generic_error():
    class Bad(WalletPressPlugin):
        name = "bad_test"

        async def execute(self, tool, params):
            raise RuntimeError("kaboom")

    register_plugin(Bad())
    try:
        out = await execute_plugin_tool("bad_test", "t", {})
        assert "Plugin error" in out["error"]
    finally:
        plugins.sdk._plugins.pop("bad_test", None)


# ── plugins/__init__ auto-discovery ───────────────────────────────


def test_defi_plugins_auto_registered():
    names = {p["name"] for p in list_plugins()}
    assert {"hyperliquid", "jupiter", "gmgn", "polymarket", "0x", "staking"} <= names


def test_exports():
    for attr in plugins.__all__:
        if attr == "_plugins":
            # imported as _plugin_registry alias
            assert hasattr(plugins, "_plugin_registry")
        else:
            assert hasattr(plugins, attr)


# ── defi plugin behavior ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_gmgn_execute():
    out = await execute_plugin_tool("gmgn", "gmgn_buy", {"token": "BONK", "sol_amount": 1})
    assert out["trade"]["token"] == "BONK"
    assert out["referral"] == defi.REF_GMGN
    assert out["revenue"] == "40%"


@pytest.mark.asyncio
async def test_lulo_execute():
    out = await execute_plugin_tool("lulo", "lulo_deposit", {"amount": 100})
    assert out == {"action": "lulo_deposit", "amount": 100, "status": "simulated"}


@pytest.mark.asyncio
async def test_zerox_execute():
    out = await execute_plugin_tool(
        "0x", "0x_quote", {"sell_token": "ETH", "buy_token": "USDC", "sell_amount": "1"}
    )
    assert out["revenue"]["platform"] == "0x"


@pytest.mark.asyncio
async def test_hyperliquid_execute():
    out = await execute_plugin_tool(
        "hyperliquid", "hl_market_order", {"coin": "BTC", "sz": 1, "is_buy": True}
    )
    assert out["status"] == "simulated"
    assert out["revenue"]["platform"] == "Hyperliquid"


@pytest.mark.asyncio
async def test_jupiter_swap_prepared():
    out = await execute_plugin_tool(
        "jupiter",
        "jupiter_swap",
        {"wallet_id": "w1", "input_mint": "SOL", "output_mint": "USDC", "amount": 1},
    )
    assert out["swap_prepared"] is True


@pytest.mark.asyncio
async def test_jupiter_quote_mocked_http(monkeypatch):
    class _Resp:
        status_code = 200

        def json(self):
            return {"outAmount": "100"}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            assert "quote-api.jup.ag" in url
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _Client())
    out = await execute_plugin_tool(
        "jupiter",
        "jupiter_quote",
        {"input_mint": "SOL", "output_mint": "USDC", "amount": 1},
    )
    assert out["outAmount"] == "100"
    assert out["revenue"]["platform"] == "Jupiter"


@pytest.mark.asyncio
async def test_jupiter_unknown_tool():
    out = await execute_plugin_tool("jupiter", "jupiter_bogus", {})
    assert "Unknown" in out["error"]


@pytest.mark.asyncio
async def test_coingecko_price_mocked(monkeypatch):
    class _Resp:
        status_code = 200

        def json(self):
            return {"solana": {"usd": 100.0}}

    class _Client:
        async def get(self, url):
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _Client())
    out = await execute_plugin_tool("coingecko", "price", {"coin_id": "solana"})
    assert out == {"solana": {"usd": 100}}


def test_plugin_tools_have_required_fields():
    tools = get_all_tools()
    assert tools
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
