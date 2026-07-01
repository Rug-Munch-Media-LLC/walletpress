"""Multi-chain transaction broadcaster via public RPC.

Broadcasts signed transactions to the network. Supports all EVM chains,
Solana, Bitcoin-family, and TRON.

Trust: We broadcast exactly what you give us. We never modify transactions,
never inspect contents, and never log private keys. The transaction must
already be signed by the wallet's private key.
"""

from __future__ import annotations

import logging

import httpx

from .balance_fetcher import EVM_RPC, SOLANA_RPC, TRON_RPC

logger = logging.getLogger("wp.tx")

BLOCKCHAIR_PUSH = "https://api.blockchair.com/{slug}/push/transaction"


async def broadcast(chain: str, signed_tx: str) -> dict:
    chain = chain.lower()
    if chain in EVM_RPC:
        return await _evm_broadcast(chain, signed_tx)
    if chain == "sol":
        return await _solana_broadcast(signed_tx)
    if chain == "trx":
        return await _tron_broadcast(signed_tx)
    if chain in ("btc", "ltc", "doge", "bch", "dash", "zec"):
        return await _btc_family_broadcast(chain, signed_tx)
    return {"broadcast": False, "error": f"No broadcast support for {chain}"}


async def _evm_broadcast(chain: str, signed_tx: str) -> dict:
    rpc_url = EVM_RPC.get(chain)
    if not rpc_url:
        return {"broadcast": False, "error": f"No RPC for {chain}"}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(rpc_url, json={
                "jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction",
                "params": [signed_tx],
            })
            data = r.json()
        if "result" in data:
            return {"broadcast": True, "tx_hash": data["result"], "chain": chain}
        return {"broadcast": False, "error": data.get("error", {}).get("message", "unknown")}
    except Exception as e:
        return {"broadcast": False, "error": str(e)}


async def _solana_broadcast(signed_tx: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(SOLANA_RPC, json={
                "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
                "params": [signed_tx, {"encoding": "base64", "skipPreflight": True}],
            })
            data = r.json()
        if "result" in data:
            return {"broadcast": True, "tx_hash": data["result"], "chain": "sol"}
        return {"broadcast": False, "error": data.get("error", {}).get("message", "unknown")}
    except Exception as e:
        return {"broadcast": False, "error": str(e)}


async def _tron_broadcast(signed_tx: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{TRON_RPC}/wallet/broadcasttransaction", json={
                "transaction": signed_tx,
            })
            data = r.json()
        if data.get("result"):
            return {"broadcast": True, "tx_hash": data.get("txid", ""), "chain": "trx"}
        return {"broadcast": False, "error": data.get("Error", "unknown")}
    except Exception as e:
        return {"broadcast": False, "error": str(e)}


async def _btc_family_broadcast(chain: str, signed_tx: str) -> dict:
    slug_map = {"btc": "bitcoin", "ltc": "litecoin", "doge": "dogecoin",
                "bch": "bitcoin-cash", "dash": "dash", "zec": "zcash"}
    slug = slug_map.get(chain, "bitcoin")
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(BLOCKCHAIR_PUSH.format(slug=slug), json={"data": signed_tx})
            data = r.json()
        if data.get("data", {}).get("transaction_hash"):
            return {"broadcast": True, "tx_hash": data["data"]["transaction_hash"], "chain": chain}
        return {"broadcast": False, "error": data.get("context", {}).get("error", "unknown")}
    except Exception as e:
        return {"broadcast": False, "error": str(e)}
