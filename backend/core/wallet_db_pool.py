"""Shared SQLite connection pool — WAL mode, thread-safe, connection reuse.

Every module that needs SQLite should use this instead of creating
ad-hoc connections. Fixes the "database is locked" errors from
connection-per-call patterns across agent_safety, smart_wallet,
scheduler, and x402 modules.
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any


class _PooledConn:
    __slots__ = ("conn", "in_use", "last_used")

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.last_used = time.monotonic()
        self.in_use = False


class DbPool:
    """Thread-safe SQLite connection pool with WAL mode and LRU eviction.

    Usage:
        pool = DbPool("/data/myapp.db", max_size=8)
        with pool.connect() as conn:
            conn.execute("SELECT 1")
    """

    def __init__(self, db_path: Path | str, max_size: int = 8, busy_timeout: int = 5000):
        self._path = Path(db_path)
        self._max_size = max_size
        self._busy_timeout = busy_timeout
        self._lock = threading.Lock()
        self._pool: OrderedDict[str, _PooledConn] = OrderedDict()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _new_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self._path), timeout=self._busy_timeout / 1000, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            f"PRAGMA busy_timeout={self._busy_timeout}"
        )  # nosemgrep: sqlalchemy-execute-raw-query — int config, no user input
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @property
    def path(self) -> Path:
        return self._path

    def connect(self):
        """Context manager that returns a pooled connection."""
        return _DbConnection(self)

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.connect() as conn:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur

    def executescript(self, sql: str) -> None:
        with self.connect() as conn:
            conn.executescript(sql)

    def _acquire(self) -> sqlite3.Connection:
        with self._lock:
            now = time.monotonic()
            for key in list(self._pool.keys()):
                pc = self._pool[key]
                if not pc.in_use:
                    pc.in_use = True
                    pc.last_used = now
                    self._pool.move_to_end(key)
                    return pc.conn

            if len(self._pool) < self._max_size:
                key = f"conn_{len(self._pool)}"
                conn = self._new_conn()
                pc = _PooledConn(conn)
                pc.in_use = True
                self._pool[key] = pc
                return conn

            oldest_key = next(iter(self._pool.keys()))
            pc = self._pool[oldest_key]
            with contextlib.suppress(Exception):
                pc.conn.close()
            conn = self._new_conn()
            pc.conn = conn
            pc.in_use = True
            pc.last_used = now
            self._pool.move_to_end(oldest_key)
            return conn

    def _release(self, conn: sqlite3.Connection) -> None:
        with self._lock:
            for pc in self._pool.values():
                if pc.conn is conn:
                    pc.in_use = False
                    pc.last_used = time.monotonic()
                    return

    def close_all(self) -> None:
        with self._lock:
            for pc in self._pool.values():
                with contextlib.suppress(Exception):
                    pc.conn.close()
            self._pool.clear()


class _DbConnection:
    def __init__(self, pool: DbPool):
        self._pool = pool
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self._conn = self._pool._acquire()
        return self._conn

    def __exit__(self, *args: Any) -> None:
        if self._conn is not None:
            self._pool._release(self._conn)
            self._conn = None
