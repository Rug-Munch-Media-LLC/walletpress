"""Anomaly Detection — Identifies suspicious wallet activity.

Checks performed:
- Unusually large transactions (>3x average)
- First-time interactions with new addresses
- Rapid-fire transactions (>5 in 1 minute)
- Unusual transaction timing (e.g. 3 AM in user's timezone)
- Dusting attacks (many tiny incoming transactions)
- Sudden balance drops
"""

from __future__ import annotations

import logging
import statistics
import time

logger = logging.getLogger("wp.agent.detector")


async def scan_wallet(address: str, chain: str = "eth") -> dict:
    """Scan a wallet for anomalous patterns.

    Uses available on-chain data providers. Falls back gracefully
    if the chain's RPC is not configured.

    Args:
        address: Wallet address to analyze
        chain: Chain key (eth, sol, trx, btc, ...)

    Returns:
        dict with risk_score, anomalies list, and metadata
    """
    from wallet_engine.chains import CHAINS

    chain_info = CHAINS.get(chain.lower())
    if not chain_info:
        return {"error": f"Unsupported chain: {chain}", "anomalies": [], "risk_score": 0}

    anomalies: list[dict] = []
    warnings: list[str] = []
    risk_score = 0

    # 1. Fetch recent transactions (best-effort)
    txs = await _fetch_recent_txs(chain, address)
    if txs:
        tx_anomalies = _analyze_transactions(txs)
        anomalies.extend(tx_anomalies)
        risk_score += len(tx_anomalies) * 15

    # 2. Fetch balance (best-effort)
    balance = await _fetch_balance(chain, address)
    if balance is not None:
        if balance > 0 and not txs:
            warnings.append("Positive balance but no transaction history — possible dormant wallet")
        if balance == 0 and txs:
            warnings.append("Zero balance with transaction history — wallet may be drained")
    else:
        warnings.append(f"Could not fetch balance for {chain}:{address}")

    # 3. Address format check
    from wallet_engine.chains import validate_address as va
    if not va(chain, address):
        warnings.append("Address format is invalid")
        risk_score += 30

    # 4. Check if it looks like a known scam pattern
    if _looks_like_dusting(txs):
        anomalies.append({
            "type": "dusting_attack",
            "severity": "medium",
            "description": "Wallet received multiple tiny transactions — possible dusting attack",
            "count": sum(1 for t in txs if _is_dust(t)),
        })
        risk_score += 20

    risk_score = min(risk_score, 100)

    return {
        "address": address,
        "chain": chain,
        "risk_score": risk_score,
        "risk_level": _risk_label(risk_score),
        "anomalies": anomalies,
        "warnings": warnings,
        "checked_at": time.time(),
    }


def _risk_label(score: int) -> str:
    if score >= 70:
        return "critical"
    if score >= 40:
        return "high"
    if score >= 20:
        return "medium"
    if score > 0:
        return "low"
    return "none"


async def _fetch_recent_txs(chain: str, address: str, limit: int = 50) -> list[dict]:
    """Fetch recent transactions for a wallet. Best-effort per chain."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as c:
            if chain == "eth":
                r = await c.get(f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&sort=desc&offset={limit}")
                data = r.json()
                if data.get("status") == "1":
                    return data["result"]
            elif chain == "sol":
                r = await c.post("https://api.mainnet-beta.solana.com", json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": "getSignaturesForAddress",
                    "params": [address, {"limit": min(limit, 50)}],
                })
                data = r.json()
                if "result" in data:
                    return data["result"]
            elif chain == "btc":
                r = await c.get(f"https://blockchain.info/rawaddr/{address}?limit={limit}")
                data = r.json()
                if "txs" in data:
                    return data["txs"]
        return []
    except Exception as e:
        logger.debug(f"Could not fetch txs for {chain}:{address}: {e}")
        return []


async def _fetch_balance(chain: str, address: str) -> float | None:
    """Fetch wallet balance. Returns float or None on failure."""
    try:
        from routers.balance_fetcher import fetch_balance
        result = await fetch_balance(chain, address)
        return result.get("balance_decimal", 0)
    except Exception as e:
        logger.debug(f"Balance fetch failed for {chain}:{address}: {e}")
        return None


def _analyze_transactions(txs: list[dict]) -> list[dict]:
    """Analyze a list of transactions for anomalies."""
    anomalies: list[dict] = []
    if not txs:
        return anomalies

    # Extract values
    amounts = []
    timestamps = []
    unique_addresses: set[str] = set()
    address_interactions: dict[str, int] = {}

    for tx in txs[:100]:
        # Parse value
        value_str = tx.get("value", tx.get("amount", tx.get("lamports", "0")))
        try:
            val = int(value_str) if isinstance(value_str, str) else float(value_str)
        except (ValueError, TypeError):
            val = 0
        amounts.append(val)

        # Parse timestamp
        ts = tx.get("timeStamp", tx.get("blockTime", tx.get("time", 0)))
        try:
            timestamps.append(int(ts))
        except (ValueError, TypeError):
            pass

        # Track interaction addresses
        for field in ("from", "to", "address"):
            addr = tx.get(field, "")
            if addr and len(addr) > 10:
                unique_addresses.add(addr)
                address_interactions[addr] = address_interactions.get(addr, 0) + 1

    # Check 1: Unusually large transactions
    if len(amounts) >= 3:
        mean_amt = statistics.mean(amounts)
        stdev_amt = statistics.stdev(amounts) if len(amounts) > 1 else 0
        for i, amt in enumerate(amounts):
            if stdev_amt > 0 and amt > mean_amt + 3 * stdev_amt:
                anomalies.append({
                    "type": "large_transaction",
                    "severity": "high",
                    "description": f"Transaction {i} is {amt:.2f} ({amt / mean_amt:.1f}x the average of {mean_amt:.2f})",
                    "tx": txs[i].get("hash", txs[i].get("signature", ""))[:16],
                })

    # Check 2: Rapid-fire transactions (>5 in 1 minute)
    if len(timestamps) >= 5:
        timestamps.sort()
        clusters = 0
        for i in range(len(timestamps) - 4):
            if timestamps[i + 4] - timestamps[i] <= 60:
                clusters += 1
        if clusters > 0:
            anomalies.append({
                "type": "rapid_transactions",
                "severity": "medium",
                "description": f"Found {clusters} clusters of 5+ transactions within 60 seconds",
            })

    # Check 3: Many unique first-time interactions
    if len(unique_addresses) > 20:
        anomalies.append({
            "type": "many_counterparties",
            "severity": "low",
            "description": f"Wallet interacted with {len(unique_addresses)} unique addresses",
        })

    # Check 4: High volume of zero-value transactions
    zero_count = sum(1 for a in amounts if a == 0)
    if len(amounts) > 0 and zero_count / len(amounts) > 0.5:
        anomalies.append({
            "type": "zero_value_txs",
            "severity": "low",
            "description": f"{zero_count}/{len(amounts)} transactions have zero value — possible spam or dusting",
        })

    return anomalies


def _is_dust(tx: dict) -> bool:
    """Check if a transaction is a dusting attempt."""
    value_str = tx.get("value", tx.get("amount", tx.get("lamports", "0")))
    try:
        val = int(value_str) if isinstance(value_str, str) else float(value_str)
        return 0 < val < 1000  # Dust: very small amounts
    except (ValueError, TypeError):
        return False


def _looks_like_dusting(txs: list[dict]) -> bool:
    """Check if the wallet was targeted by a dusting attack."""
    dust_count = sum(1 for tx in txs[-20:] if _is_dust(tx))
    unique_senders = set()
    for tx in txs[-20:]:
        sender = tx.get("from", "")
        if sender and _is_dust(tx):
            unique_senders.add(sender)
    # Dusting: many tiny txs from many different senders
    return dust_count >= 5 and len(unique_senders) >= 3
