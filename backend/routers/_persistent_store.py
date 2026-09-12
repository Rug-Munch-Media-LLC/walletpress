"""Persistent store for chain_vault router — webhooks, alerts, payments, etc.

SQLite-backed key-value store. Each collection is a table with a JSON
blob column. Lazy-initialized on first access. Survives server restarts.

Extracted from chain_vault.py in Phase 5 refactor to reduce god-file size.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import TYPE_CHECKING

from core.config import cfg

if TYPE_CHECKING:
    from pathlib import Path


class PersistentStore:
    """SQLite-backed JSON-blob store for small collections.

    Used by chain_vault router for webhooks, alerts, payments. Each
    collection is its own table; rows store JSON-serialized dicts.

    Thread-safe via check_same_thread=False + WAL mode. Use sparingly
    — for high-throughput data, use a real DB.
    """

    _db: sqlite3.Connection | None = None
    # Allowlisted table names — never interpolate user input into SQL.
    _TABLES = frozenset({"webhooks", "alerts", "payments"})

    @classmethod
    def _table(cls, table: str) -> str:
        """Validate a table name against the allowlist before SQL interpolation."""
        if table not in cls._TABLES:
            raise ValueError(f"Unknown table: {table}")
        return table

    @classmethod
    def _get_db(cls) -> sqlite3.Connection:
        if cls._db is None:
            db_path: Path = cfg.data_dir / "chain_vault_store.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            cls._db = sqlite3.connect(str(db_path), check_same_thread=False)
            cls._db.row_factory = sqlite3.Row
            cls._db.execute("PRAGMA journal_mode=WAL")
            cls._db.execute("PRAGMA busy_timeout=5000")
            cls._db.executescript("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS payments (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """)
        return cls._db

    @classmethod
    def all(cls, table: str) -> list[dict]:
        db = cls._get_db()
        rows = db.execute(  # nosemgrep: sqlalchemy-execute-raw-query — allowlisted table + parameterized values
            f"SELECT data FROM {cls._table(table)} ORDER BY created_at DESC"  # noqa: S608 — table validated against _TABLES allowlist
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    @classmethod
    def get(cls, table: str, item_id: str) -> dict | None:
        db = cls._get_db()
        row = db.execute(  # nosemgrep: sqlalchemy-execute-raw-query — allowlisted table + parameterized values
            f"SELECT data FROM {cls._table(table)} WHERE id = ?",  # noqa: S608 — table validated against _TABLES allowlist
            (item_id,),
        ).fetchone()
        return json.loads(row["data"]) if row else None

    @classmethod
    def put(cls, table: str, item: dict) -> None:
        db = cls._get_db()
        db.execute(  # nosemgrep: sqlalchemy-execute-raw-query — allowlisted table + parameterized values
            f"INSERT OR REPLACE INTO {cls._table(table)} (id, data, created_at) VALUES (?, ?, ?)",  # noqa: S608 — table validated against _TABLES allowlist
            (item["id"], json.dumps(item), item.get("created_at", time.time())),
        )
        db.commit()

    @classmethod
    def delete(cls, table: str, item_id: str) -> None:
        db = cls._get_db()
        db.execute(  # nosemgrep: sqlalchemy-execute-raw-query — allowlisted table + parameterized values
            f"DELETE FROM {cls._table(table)} WHERE id = ?",  # noqa: S608 — table validated against _TABLES allowlist
            (item_id,),
        )
        db.commit()

    @classmethod
    def reload_webhooks(cls) -> None:
        """Reload webhooks from DB into the live deliverer on startup."""
        from core.webhooks import get_webhook_deliverer

        deliverer = get_webhook_deliverer()
        webhooks = cls.all("webhooks")
        for wh in webhooks:
            if wh.get("active", True):
                deliverer.register(wh["id"], wh["url"], wh.get("secret", ""), wh.get("events", []))
