"""Persistent store for chain_vault router — webhooks, alerts, payments, etc.

SQLite-backed key-value store. Each collection is a table with a JSON
blob column. Lazy-initialized on first access. Survives server restarts.

Extracted from chain_vault.py in Phase 5 refactor to reduce god-file size.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from core.config import cfg


class PersistentStore:
    """SQLite-backed JSON-blob store for small collections.

    Used by chain_vault router for webhooks, alerts, payments. Each
    collection is its own table; rows store JSON-serialized dicts.

    Thread-safe via check_same_thread=False + WAL mode. Use sparingly
    — for high-throughput data, use a real DB.
    """

    _db: sqlite3.Connection | None = None

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
        rows = db.execute(f"SELECT data FROM {table} ORDER BY created_at DESC").fetchall()
        return [json.loads(r["data"]) for r in rows]

    @classmethod
    def get(cls, table: str, item_id: str) -> dict | None:
        db = cls._get_db()
        row = db.execute(f"SELECT data FROM {table} WHERE id = ?", (item_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    @classmethod
    def put(cls, table: str, item: dict) -> None:
        db = cls._get_db()
        db.execute(
            f"INSERT OR REPLACE INTO {table} (id, data, created_at) VALUES (?, ?, ?)",
            (item["id"], json.dumps(item), item.get("created_at", time.time())),
        )
        db.commit()

    @classmethod
    def delete(cls, table: str, item_id: str) -> None:
        db = cls._get_db()
        db.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
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