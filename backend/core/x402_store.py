"""SQLite persistence for the x402 marketplace payment gate.

Deliberately dumb: every function takes the database path explicitly, so the
service facade owns configuration and tests can point at a temp file. Only the
gate's own tables live here — orders and per-client free-tier usage. No pricing
policy, no HTTP, no wallet logic.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_EXEC = "CREATE TABLE IF NOT EXISTS"

SCHEMA = """
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY, chain TEXT NOT NULL,
        count INTEGER NOT NULL, amount_usd REAL NOT NULL,
        payment_tx TEXT DEFAULT '', payment_status TEXT DEFAULT 'pending',
        status TEXT DEFAULT 'pending', created_at REAL NOT NULL,
        client_ip TEXT DEFAULT '',
        idempotency_key TEXT DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_orders_idempotency ON orders(idempotency_key);
    CREATE TABLE IF NOT EXISTS free_tier_usage (
        client_ip TEXT PRIMARY KEY, wallets INTEGER NOT NULL DEFAULT 0
    );
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open (and lazily create) the gate database in WAL mode."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def free_wallets_used(db_path: Path, client_ip: str) -> int:
    """Count free-tier wallets already issued to this client."""
    conn = connect(db_path)
    row = conn.execute(
        "SELECT COALESCE(SUM(wallets), 0) FROM free_tier_usage WHERE client_ip = ?",
        (client_ip,),
    ).fetchone()
    conn.close()
    return int(row[0]) if row and row[0] else 0


def record_free_usage(db_path: Path, client_ip: str, count: int) -> None:
    """Add free-tier wallets to this client's running total."""
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO free_tier_usage (client_ip, wallets) VALUES (?, ?) "
        "ON CONFLICT(client_ip) DO UPDATE SET wallets = wallets + ?",
        (client_ip, count, count),
    )
    conn.commit()
    conn.close()


def find_order_by_idempotency(db_path: Path, idempotency_key: str) -> dict | None:
    """Return the recorded order for a replayed idempotency key, if any."""
    if not idempotency_key:
        return None
    conn = connect(db_path)
    row = conn.execute(
        "SELECT * FROM orders WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_order(
    db_path: Path,
    *,
    order_id: str,
    chain: str,
    count: int,
    amount_usd: float,
    payment_tx: str,
    client_ip: str,
    idempotency_key: str,
) -> None:
    """Record a completed order."""
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO orders (order_id, chain, count, amount_usd, payment_tx, "
        "payment_status, status, created_at, client_ip, idempotency_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            order_id,
            chain,
            count,
            amount_usd,
            payment_tx or "free",
            "confirmed",
            "completed",
            time.time(),
            client_ip,
            idempotency_key or "",
        ),
    )
    conn.commit()
    conn.close()
