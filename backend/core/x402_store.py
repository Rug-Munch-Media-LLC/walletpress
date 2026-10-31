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
        idempotency_key TEXT DEFAULT '',
        client_identity TEXT DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_orders_idempotency ON orders(idempotency_key);
    CREATE INDEX IF NOT EXISTS idx_orders_idem_client
        ON orders(idempotency_key, client_identity);
    CREATE TABLE IF NOT EXISTS free_tier_usage (
        client_ip TEXT PRIMARY KEY, wallets INTEGER NOT NULL DEFAULT 0
    );
"""


def connect(db_path: Path, timeout: float = 15.0) -> sqlite3.Connection:
    """Open (and lazily create) the gate database in WAL mode.

    A generous busy timeout keeps concurrent writers queueing instead of
    raising "database is locked" while another thread holds the write lock.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=timeout, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.executescript(SCHEMA)
    _ensure_client_identity(conn)
    return conn


def _ensure_client_identity(conn: sqlite3.Connection) -> None:
    """Add orders.client_identity to a pre-existing database (idempotent)."

    Fixed statements only: the old generic helper built SQL by f-string
    interpolation, which semgrep flags as SQL construction (and is how an
    injection arrives once a caller-supplied name reaches it).
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
    if "client_identity" not in cols:
        conn.execute(
            "ALTER TABLE orders ADD COLUMN client_identity TEXT DEFAULT ''"
        )


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


def find_order_by_idempotency(
    db_path: Path, idempotency_key: str, client_identity: str
) -> dict | None:
    """Return this client's order for a replayed idempotency key, if any.

    Scoped to the caller's identity: an idempotency key is a client-scoped
    token, never a global handle on someone else's order (CWE-639).
    """
    if not idempotency_key:
        return None
    conn = connect(db_path)
    row = conn.execute(
        "SELECT * FROM orders WHERE idempotency_key = ? AND client_identity = ?",
        (idempotency_key, client_identity),
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
    client_identity: str = "",
) -> None:
    """Record a completed order."""
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO orders (order_id, chain, count, amount_usd, payment_tx, "
        "payment_status, status, created_at, client_ip, idempotency_key, "
        "client_identity) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            client_identity,
        ),
    )
    conn.commit()
    conn.close()


_USED_SQL = "SELECT COALESCE(SUM(wallets), 0) FROM free_tier_usage WHERE client_ip = ?"
_ADD_SQL = (
    "INSERT INTO free_tier_usage (client_ip, wallets) VALUES (?, ?) "
    "ON CONFLICT(client_ip) DO UPDATE SET wallets = wallets + ?"
)


def reserve_free_quota(
    db_path: Path, client_ip: str, count: int, limit: int, *, attempts: int = 3
) -> tuple[bool, int]:
    """Atomically grant up to 'limit' free wallets to one client.

    Returns (granted, wallets_used_before). The quota read and the increment
    happen inside a single BEGIN IMMEDIATE transaction, so concurrent requests
    can never jointly exceed the quota (CWE-362). Writers queue on the sqlite
    write lock instead of interleaving; a busy lock is retried, never granted.
    """
    for attempt in range(1, attempts + 1):
        conn = connect(db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(_USED_SQL, (client_ip,)).fetchone()
            used = int(row[0]) if row and row[0] else 0
            if used + count > limit:
                conn.execute("ROLLBACK")
                return False, used
            conn.execute(_ADD_SQL, (client_ip, count, count))
            conn.execute("COMMIT")
            return True, used
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or attempt == attempts:
                raise
        finally:
            conn.close()
    raise AssertionError("reserve_free_quota: retry loop exhausted")


def release_free_quota(db_path: Path, client_ip: str, count: int) -> None:
    """Return reserved free-tier wallets after a failed order (fail-closed)."""
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE free_tier_usage SET wallets = MAX(wallets - ?, 0) WHERE client_ip = ?",
            (count, client_ip),
        )
    finally:
        conn.close()
