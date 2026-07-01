"""Wallet health monitoring — proactive security for vault wallets.

Monitors wallet balances, age, rotation status, and security posture.
Sends alerts when action is needed.

Like Credit Karma for your crypto wallets.
Revenue model: $29/mo SaaS or $99 one-time add-on.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config import cfg
from core.vault import get_vault

logger = logging.getLogger("wp.health")

router = APIRouter(prefix="/api/v1/health", tags=["Health Monitor"])

_monitor_db: Optional[sqlite3.Connection] = None


def _get_db() -> sqlite3.Connection:
    global _monitor_db
    if _monitor_db is None:
        db_path = cfg.data_dir / "health_monitor.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _monitor_db = sqlite3.connect(str(db_path))
        _monitor_db.row_factory = sqlite3.Row
        _monitor_db.execute("PRAGMA journal_mode=WAL")
        _monitor_db.executescript("""
            CREATE TABLE IF NOT EXISTS health_scores (
                wallet_id TEXT NOT NULL,
                score INTEGER NOT NULL,
                age_days REAL,
                balance_usd REAL DEFAULT 0,
                rotation_count INTEGER DEFAULT 0,
                encrypted INTEGER DEFAULT 0,
                    red_flags TEXT DEFAULT '[]',
                checked_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS monitor_config (
                wallet_id TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                check_interval_hours REAL DEFAULT 24,
                low_balance_threshold REAL DEFAULT 10.0,
                alert_email TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_health_wallet ON health_scores(wallet_id);
        """)
        _monitor_db.commit()
    return _monitor_db


class HealthAlert(BaseModel):
    wallet_id: str
    score: int
    old_score: int = 0
    red_flags: list[str] = Field(default_factory=list)
    checked_at: float = 0.0


def _compute_health(wallet_id: str) -> dict:
    """Compute wallet health score (0-100)."""
    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        return {"error": "Wallet not found"}

    rotations = vault.get_rotations(wallet_id)
    age_days = (time.time() - wallet.created_at) / 86400 if wallet.created_at else 0

    score = 100
    red_flags = []

    if age_days > 365:
        score -= 10
        red_flags.append("Wallet is over 1 year old — consider rotating")
    if wallet.balance_usd == 0:
        score -= 15
        red_flags.append("Zero balance — wallet may be unused")
    if wallet.encrypted_key and wallet.encrypted:
        score += 5
    else:
        score -= 10
        red_flags.append("Private key stored in plaintext — enable encryption")
    if len(rotations) > 0:
        score += min(len(rotations) * 5, 20)
    else:
        score -= 5
        red_flags.append("Wallet has never been rotated")

    score = max(0, min(100, score))

    return {
        "wallet_id": wallet_id,
        "score": score,
        "age_days": round(age_days, 1),
        "balance_usd": wallet.balance_usd,
        "rotation_count": len(rotations),
        "encrypted": wallet.encrypted,
        "red_flags": red_flags,
    }


@router.post("/check/{wallet_id}")
async def check_wallet_health(wallet_id: str):
    """Immediately check a wallet's health score.

    Scores range 0-100:
      80-100: Healthy
      50-79: Needs attention
      0-49: Critical — take action
    """
    result = _compute_health(wallet_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    db = _get_db()
    db.execute(
        "INSERT INTO health_scores (wallet_id, score, age_days, balance_usd, rotation_count, encrypted, red_flags, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (result["wallet_id"], result["score"], result["age_days"],
         result["balance_usd"], result["rotation_count"],
         int(result["encrypted"]), json.dumps(result["red_flags"]), time.time()),
    )
    db.commit()

    return {
        "wallet_id": wallet_id,
        "health": result,
        "status": "healthy" if result["score"] >= 80 else "needs_attention" if result["score"] >= 50 else "critical",
        "recommendations": result["red_flags"],
    }


@router.get("/check/{wallet_id}/history")
async def health_history(wallet_id: str, limit: int = 30):
    """Get health score history for a wallet."""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM health_scores WHERE wallet_id = ? ORDER BY checked_at DESC LIMIT ?",
        (wallet_id, limit),
    ).fetchall()
    return {
        "wallet_id": wallet_id,
        "history": [dict(r) for r in rows],
    }


_health_cache: dict[str, dict] = {}
_HEALTH_CACHE_TTL = 300  # 5 minutes


def _cached_health(wallet_id: str) -> dict:
    now = time.time()
    cached = _health_cache.get(wallet_id)
    if cached and now - cached.get("_cached_at", 0) < _HEALTH_CACHE_TTL:
        return cached
    result = _compute_health(wallet_id)
    result["_cached_at"] = now
    _health_cache[wallet_id] = result
    return result


@router.get("/dashboard")
async def health_dashboard(page: int = 1, per_page: int = 50):
    """Get health overview for all vault wallets (paginated).

    Returns summary stats plus a page of wallet health scores.
    Use ?page= and ?per_page= to paginate through results.
    """
    vault = get_vault()
    wallets = vault.list(limit=10000)
    results = []
    for w in wallets:
        h = _cached_health(w.id)
        if "score" in h:
            results.append(h)

    total = len(results)
    start = (page - 1) * per_page
    end = start + per_page
    page_results = results[start:end]

    healthy = sum(1 for r in results if r["score"] >= 80)
    attention = sum(1 for r in results if 50 <= r["score"] < 80)
    critical = sum(1 for r in results if r["score"] < 50)

    return {
        "total_wallets": total,
        "healthy": healthy,
        "needs_attention": attention,
        "critical": critical,
        "average_score": round(sum(r["score"] for r in results) / total, 1) if results else 0,
        "lowest_score_wallet": min(results, key=lambda r: r["score"]) if results else None,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "wallets": page_results,
    }


@router.get("/alerts")
async def health_alerts(threshold: int = 50):
    """Get wallets with health scores below threshold."""
    vault = get_vault()
    wallets = vault.list(limit=10000)
    alerts = []
    for w in wallets:
        h = _cached_health(w.id)
        if h.get("score", 100) < threshold:
            alerts.append({
                "wallet_id": w.id,
                "address": w.address,
                "chain": w.chain,
                "score": h["score"],
                "red_flags": h.get("red_flags", []),
            })
    return {"alerts": alerts, "total": len(alerts), "threshold": threshold}
