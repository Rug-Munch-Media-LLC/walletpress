"""Encrypted wallet vault — AES-256-GCM + Argon2id, stored in SQLite.

Trust principle: The vault password NEVER leaves the server. If you use
client-side generation, the private key is encrypted before it ever reaches
the server. The server stores opaque blobs it cannot decrypt.

Server-side generation (enterprise vault) encrypts keys at rest with
the vault password. The password is configurable and never logged.
"""

from __future__ import annotations

import base64
import json
import logging
import queue
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config import cfg

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

logger = logging.getLogger("wp.vault")

try:
    from argon2.low_level import Type as _Argon2Type, hash_secret_raw as _argon2id_kdf
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    raise RuntimeError(
        "cryptography and argon2-cffi are required. Install them: pip install cryptography>=42.0.0 argon2-cffi>=23.0.0"
    ) from None


@dataclass
class WalletEntry:
    id: str
    chain: str
    address: str
    label: str
    tags: list[str] = field(default_factory=list)
    group: str = ""
    created_at: float = 0.0
    encrypted_key: str = ""
    public_key: str = ""
    derivation_path: str = ""
    hd_path: str = ""
    mnemonic_encrypted: str = ""
    encrypted: bool = False
    balance_usd: float = 0.0
    notes: str = ""


class Vault:
    """Encrypted wallet vault with pooled SQLite connections.

    Connection pool: up to POOL_SIZE reusable connections, thread-safe.
    WAL mode + busy_timeout prevent 'database is locked' under concurrent load.
    """

    POOL_SIZE = 8
    BUSY_TIMEOUT = 5000  # ms before raising locked error

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=self.POOL_SIZE)
        self._lock = threading.Lock()
        self._total_conns = 0
        if not cfg.vault_password:
            raise RuntimeError(
                "WalletPress vault requires encryption. "
                "Set WP_VAULT_PASSWORD environment variable to a strong password. "
                "Example: export WP_VAULT_PASSWORD='$(openssl rand -base64 32)'"
            )
        self._init_db()

    def _new_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path), timeout=self.BUSY_TIMEOUT / 1000, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query — int config, no user input
            f"PRAGMA busy_timeout={self.BUSY_TIMEOUT}"
        )
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """Get a connection from the pool (or create one). Auto-returns on exit."""
        try:
            conn = self._pool.get_nowait()
        except queue.Empty:
            with self._lock:
                if self._total_conns < self.POOL_SIZE:
                    conn = self._new_conn()
                    self._total_conns += 1
                else:
                    conn = self._new_conn()  # overflow — will close after use
        try:
            yield conn
        finally:
            try:
                self._pool.put_nowait(conn)
            except queue.Full:
                conn.close()
                with self._lock:
                    self._total_conns -= 1

    SCHEMA_VERSION = 1

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._new_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS wallets (
                id TEXT PRIMARY KEY,
                chain TEXT NOT NULL,
                address TEXT NOT NULL,
                label TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                wallet_group TEXT DEFAULT '',
                created_at REAL NOT NULL,
                encrypted_key TEXT DEFAULT '',
                public_key TEXT DEFAULT '',
                derivation_path TEXT DEFAULT '',
                hd_path TEXT DEFAULT '',
                mnemonic_encrypted TEXT DEFAULT '',
                encrypted INTEGER DEFAULT 0,
                balance_usd REAL DEFAULT 0.0,
                notes TEXT DEFAULT '',
                updated_at REAL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_wallets_chain ON wallets(chain);
            CREATE INDEX IF NOT EXISTS idx_wallets_address ON wallets(address);
            CREATE VIRTUAL TABLE IF NOT EXISTS wallets_fts USING fts5(
                id, chain, address, label, notes,
                content='wallets',
                content_rowid='rowid'
            );
            CREATE TABLE IF NOT EXISTS rotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id TEXT NOT NULL,
                new_address TEXT NOT NULL,
                rotated_at REAL NOT NULL,
                reason TEXT DEFAULT '',
                FOREIGN KEY(wallet_id) REFERENCES wallets(id)
            );
            CREATE TABLE IF NOT EXISTS _schema_version (
                version INTEGER PRIMARY KEY,
                applied_at REAL NOT NULL
            );
        """)
            conn.commit()
            self._migrate(conn)

    def _migrate(self, conn):
        # P3-5: Schema migrations are now handled by Alembic. This stub
        # only stamps the schema version table. Kept for backward compat
        # with existing DBs that have _schema_version rows.
        row = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()
        current = row[0] if row and row[0] else 0
        if current >= self.SCHEMA_VERSION:
            return
        with self._lock:
            conn.execute(
                "INSERT OR IGNORE INTO _schema_version (version, applied_at) VALUES (?, ?)",
                (self.SCHEMA_VERSION, time.time()),
            )
            conn.commit()
            logger.info(
                f"Vault schema version stamped at v{self.SCHEMA_VERSION}. "
                f"For real schema migrations, run `alembic upgrade head`."
            )

    def encrypt_key(self, plaintext: str) -> str:
        salt = secrets.token_bytes(16)
        key = _argon2id_kdf(
            secret=cfg.vault_password.encode(),
            salt=salt,
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
            type=_Argon2Type.ID,
        )
        aesgcm = AESGCM(key)
        nonce = secrets.token_bytes(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(salt + nonce + ct).decode()

    def decrypt_key(self, encrypted: str) -> str:
        data = base64.b64decode(encrypted)
        salt, nonce, ct = data[:16], data[16:28], data[28:]
        key = _argon2id_kdf(
            secret=cfg.vault_password.encode(),
            salt=salt,
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
            type=_Argon2Type.ID,
        )
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode()

    def put(self, wallet: WalletEntry) -> bool:
        with self._conn() as conn:
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO wallets
                    (id, chain, address, label, tags, wallet_group, created_at, encrypted_key,
                     public_key, derivation_path, hd_path, mnemonic_encrypted,
                     encrypted, balance_usd, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        wallet.id,
                        wallet.chain,
                        wallet.address,
                        wallet.label,
                        json.dumps(wallet.tags),
                        wallet.group,
                        wallet.created_at or time.time(),
                        wallet.encrypted_key,
                        wallet.public_key,
                        wallet.derivation_path,
                        wallet.hd_path,
                        wallet.mnemonic_encrypted,
                        int(wallet.encrypted),
                        wallet.balance_usd,
                        wallet.notes,
                        time.time(),
                    ),
                )
                conn.commit()
                self.update_fts(wallet)
                return True
            except Exception as e:
                logger.error(f"Vault put failed: {e}")
                return False

    def get(self, wallet_id: str) -> WalletEntry | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    def get_by_address(self, address: str) -> WalletEntry | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM wallets WHERE address = ?", (address,)).fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    def list(self, chain: str = "", limit: int = 100, offset: int = 0) -> list[WalletEntry]:
        with self._conn() as conn:
            if chain:
                rows = conn.execute(
                    "SELECT * FROM wallets WHERE chain = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (chain, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM wallets ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [self._row_to_entry(r) for r in rows]

    def search(self, query: str) -> list[WalletEntry]:
        with self._conn() as conn:
            try:
                rows = conn.execute(
                    "SELECT wallets.* FROM wallets_fts JOIN wallets ON wallets_fts.id = wallets.id WHERE wallets_fts MATCH ? ORDER BY rank LIMIT 50",
                    (query,),
                ).fetchall()
            except Exception:
                like = f"%{query}%"
                rows = conn.execute(
                    "SELECT * FROM wallets WHERE address LIKE ? OR label LIKE ? OR chain LIKE ? OR notes LIKE ? LIMIT 50",
                    (like, like, like, like),
                ).fetchall()
            return [self._row_to_entry(r) for r in rows]

    def update_fts(self, wallet: WalletEntry):
        """Refresh the FTS index for a wallet. Non-fatal if it fails."""
        with self._conn() as conn, suppress(Exception):
            conn.execute(
                "INSERT OR REPLACE INTO wallets_fts (id, chain, address, label, notes) VALUES (?, ?, ?, ?, ?)",
                (wallet.id, wallet.chain, wallet.address, wallet.label, wallet.notes),
            )
            conn.commit()

    def delete(self, wallet_id: str) -> bool:
        with self._conn() as conn:
            conn.execute("DELETE FROM wallets WHERE id = ?", (wallet_id,))
            conn.commit()
            return conn.total_changes > 0

    def count(self, chain: str = "") -> int:
        with self._conn() as conn:
            if chain:
                return conn.execute(
                    "SELECT COUNT(*) FROM wallets WHERE chain = ?", (chain,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0]

    def record_rotation(self, wallet_id: str, new_address: str, reason: str = ""):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO rotations (wallet_id, new_address, rotated_at, reason) VALUES (?, ?, ?, ?)",
                (wallet_id, new_address, time.time(), reason),
            )
            conn.commit()

    def get_rotations(self, wallet_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM rotations WHERE wallet_id = ? ORDER BY rotated_at DESC",
                (wallet_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0]
            by_chain = conn.execute(
                "SELECT chain, COUNT(*) as count FROM wallets GROUP BY chain ORDER BY count DESC"
            ).fetchall()
            encrypted = conn.execute("SELECT COUNT(*) FROM wallets WHERE encrypted = 1").fetchone()[
                0
            ]
            return {
                "total_wallets": total,
                "encrypted_wallets": encrypted,
                "chains_used": len(by_chain),
                "by_chain": {r["chain"]: r["count"] for r in by_chain},
                "rotations": conn.execute("SELECT COUNT(*) FROM rotations").fetchone()[0],
            }

    def _row_to_entry(self, row) -> WalletEntry:
        def _g(key: str, default=""):
            try:
                val = row[key]
                return val if val is not None else default
            except (KeyError, IndexError, TypeError):
                return default

        return WalletEntry(
            id=_g("id"),
            chain=_g("chain"),
            address=_g("address"),
            label=_g("label"),
            tags=json.loads(_g("tags", "[]")),
            group=_g("wallet_group"),
            created_at=float(_g("created_at", "0")),
            encrypted_key=_g("encrypted_key"),
            public_key=_g("public_key"),
            derivation_path=_g("derivation_path"),
            hd_path=_g("hd_path"),
            mnemonic_encrypted=_g("mnemonic_encrypted"),
            encrypted=bool(_g("encrypted", "0")),
            balance_usd=float(_g("balance_usd", "0")),
            notes=_g("notes"),
        )


_vault: Vault | None = None


def get_vault() -> Vault:
    global _vault
    if _vault is None:
        _vault = Vault(cfg.db_path)
    return _vault
