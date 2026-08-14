"""Multi-chain balance fetcher using public RPC endpoints.

No API keys required for basic functionality — all data from public nodes.

Supported: EVM (all 23 chains), Solana, TRON, Bitcoin-family (5 chains),
Cosmos-family (4 chains), Substrate (2 chains), Algorand, Stellar, Filecoin.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from core.config import cfg

logger = logging.getLogger("wp.balances")

EVM_RPC = {k: v for k, v in cfg.rpc_urls().items() if k != "sol" and k != "trx"}
SOLANA_RPC = cfg.rpc_urls().get("sol", "https://api.mainnet-beta.solana.com")
TRON_RPC = cfg.rpc_urls().get("trx", "https://api.trongrid.io")


async def fetch_balance(chain: str, address: str) -> dict[str, Any]:
    chain = chain.lower()
    if chain in EVM_RPC:
        return await _evm_balance(chain, address)
    if chain == "sol":
        return await _solana_balance(address)
    if chain == "trx":
        return await _tron_balance(address)
    if chain in ("btc", "btc-segwit", "btc-native-segwit", "ltc", "doge", "bch", "dash", "zec"):
        return await _btc_family_balance(chain, address)
    if chain in ("dot", "ksm"):
        return await _substrate_balance(chain, address)
    if chain in ("atom", "osmo", "inj", "juno", "sei"):
        return await _cosmos_balance(chain, address)
    if chain == "algo":
        return await _algorand_balance(address)
    if chain == "xlm":
        return await _stellar_balance(address)
    if chain == "fil":
        return await _filecoin_balance(address)
    if chain == "xrp":
        return await _ripple_balance(address)
    if chain == "ada":
        return await _cardano_balance(address)
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "unsupported", "error": f"No balance API for {chain}"}


async def _evm_balance(chain: str, address: str) -> dict:
    rpc_url = EVM_RPC.get(chain)
    if not rpc_url:
        return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "no-rpc"}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(rpc_url, json={"jsonrpc": "2.0", "method": "eth_getBalance", "params": [address, "latest"], "id": 1})
            data = r.json()
        if "result" in data:
            wei = int(data["result"], 16)
            eth = wei / 1e18
            return {"balance": str(wei), "balance_decimal": round(eth, 6), "balance_usd": 0, "source": f"rpc:{chain}"}
    except Exception as e:
        logger.warning(f"EVM balance failed {chain}:{address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": f"rpc:{chain}"}


async def _solana_balance(address: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(SOLANA_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]})
            data = r.json()
        if "result" in data:
            lamports = data["result"]["value"]
            sol = lamports / 1e9
            return {"balance": str(lamports), "balance_decimal": round(sol, 6), "balance_usd": 0, "source": "rpc:solana"}
    except Exception as e:
        logger.warning(f"SOL balance failed {address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "rpc:solana"}


async def _tron_balance(address: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{TRON_RPC}/v1/accounts/{address}")
            data = r.json()
        if "data" in data and len(data["data"]) > 0:
            raw = int(data["data"][0].get("balance", 0))
            trx = raw / 1e6
            return {"balance": str(raw), "balance_decimal": round(trx, 6), "balance_usd": 0, "source": "rpc:tron"}
    except Exception as e:
        logger.warning(f"TRX balance failed {address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "rpc:tron"}


async def _btc_family_balance(chain: str, address: str) -> dict:
    """Bitcoin-family via blockchain.info (free, no key) and blockchair."""
    try:
        if chain == "btc":
            url = f"https://blockchain.info/balance?active={address}"
        else:
            explorer_map = {"ltc": "litecoin", "doge": "dogecoin", "bch": "bitcoin-cash", "dash": "dash", "zec": "zcash"}
            slug = explorer_map.get(chain, "bitcoin")
            url = f"https://api.blockchair.com/{slug}/dashboards/address/{address}?limit=1"
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(url)
            data = r.json()
        if chain == "btc" and address in data:
            sat = data[address].get("final_balance", 0)
            btc = sat / 1e8
            return {"balance": str(sat), "balance_decimal": round(btc, 8), "balance_usd": 0, "source": "blockchain.info"}
        if "data" in data:
            addr_data = data["data"].get(address, {})
            raw = int(addr_data.get("address", {}).get("balance", 0))
            decimals = {"ltc": 8, "doge": 8, "bch": 8, "dash": 8, "zec": 8}
            div = 10 ** decimals.get(chain, 8)
            return {"balance": str(raw), "balance_decimal": round(raw / div, 8), "balance_usd": 0, "source": "blockchair"}
    except Exception as e:
        logger.warning(f"{chain} balance failed {address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": f"blockchair:{chain}"}


async def _substrate_balance(chain: str, address: str) -> dict:
    """Polkadot/Kusama via Subscan public API."""
    subscan_map = {"dot": "polkadot", "ksm": "kusama"}
    network = subscan_map.get(chain)
    if not network:
        return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "unsupported"}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(f"https://{network}.api.subscan.io/api/scan/account/tokens", json={"address": address})
            data = r.json()
        if data.get("code") == 0 and data.get("data"):
            for token in data["data"]:
                if token.get("symbol", "").upper() == chain.upper():
                    raw = float(token.get("balance", 0))
                    decimals = 10 if chain == "dot" else 12
                    return {"balance": str(int(raw * 10**decimals)), "balance_decimal": round(raw, 4), "balance_usd": 0, "source": "subscan"}
            return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "subscan"}
    except Exception as e:
        logger.warning(f"Substrate balance failed {chain}:{address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "subscan"}


async def _cosmos_balance(chain: str, address: str) -> dict:
    """Cosmos-family via public LCD REST API."""
    rpc_map = {"atom": "https://rest.cosmos.directory/cosmoshub", "osmo": "https://rest.cosmos.directory/osmosis",
               "inj": "https://rest.cosmos.directory/injective", "juno": "https://rest.cosmos.directory/juno",
               "sei": "https://rest.cosmos.directory/sei"}
    rpc_url = rpc_map.get(chain)
    denom_map = {"atom": "uatom", "osmo": "uosmo", "inj": "inj", "juno": "ujuno", "sei": "usei"}
    denom = denom_map.get(chain, f"u{chain}")
    if not rpc_url:
        return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "no-rpc"}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{rpc_url}/cosmos/bank/v1beta1/balances/{address}/by_denom?denom={denom}")
            data = r.json()
        if "balance" in data:
            raw = int(data["balance"].get("amount", "0"))
            decimals = 6
            return {"balance": str(raw), "balance_decimal": round(raw / 10**decimals, 6), "balance_usd": 0, "source": f"cosmos:{chain}"}
    except Exception as e:
        logger.warning(f"Cosmos balance failed {chain}:{address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": f"cosmos:{chain}"}


async def _algorand_balance(address: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"https://algoexplorerapi.io/v2/accounts/{address}")
            data = r.json()
        if "amount" in data:
            raw = int(data["amount"])
            algo = raw / 1e6
            return {"balance": str(raw), "balance_decimal": round(algo, 6), "balance_usd": 0, "source": "algoexplorer"}
    except Exception as e:
        logger.warning(f"ALGO balance failed {address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "algoexplorer"}


async def _stellar_balance(address: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"https://horizon.stellar.org/accounts/{address}")
            data = r.json()
        if "balances" in data:
            for b in data["balances"]:
                if b.get("asset_type") == "native":
                    xlm = float(b["balance"])
                    raw = int(xlm * 1e7)
                    return {"balance": str(raw), "balance_decimal": round(xlm, 7), "balance_usd": 0, "source": "stellar"}
            return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "stellar"}
    except Exception as e:
        logger.warning(f"XLM balance failed {address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "stellar"}


async def _filecoin_balance(address: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post("https://api.node.glif.io/rpc/v0", json={
                "jsonrpc": "2.0", "id": 1, "method": "Filecoin.WalletBalance", "params": [address]
            })
            data = r.json()
        if "result" in data:
            raw = int(data["result"], 16) if data["result"].startswith("0x") else int(data["result"])
            fil = raw / 1e18
            return {"balance": str(raw), "balance_decimal": round(fil, 6), "balance_usd": 0, "source": "filecoin"}
    except Exception as e:
        logger.warning(f"FIL balance failed {address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "filecoin"}


async def _ripple_balance(address: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post("https://s1.ripple.com:51234", json={
                "method": "account_info", "params": [{"account": address, "strict": True}]
            })
            data = r.json()
        if data.get("result", {}).get("status") == "success":
            drops = int(data["result"]["account_data"]["Balance"])
            xrp = drops / 1e6
            return {"balance": str(drops), "balance_decimal": round(xrp, 6), "balance_usd": 0, "source": "ripple"}
    except Exception as e:
        logger.warning(f"XRP balance failed {address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "ripple"}


async def _cardano_balance(address: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"https://cardanoscan.io/api/address/{address}")
            data = r.json()
        if "totalBalance" in data:
            raw = int(data["totalBalance"])
            ada = raw / 1e6
            return {"balance": str(raw), "balance_decimal": round(ada, 6), "balance_usd": 0, "source": "cardanoscan"}
    except Exception as e:
        logger.warning(f"ADA balance failed {address}: {e}")
    return {"balance": "0", "balance_decimal": 0, "balance_usd": 0, "source": "cardanoscan"}
