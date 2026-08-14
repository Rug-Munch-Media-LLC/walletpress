"""TOTP 2FA for admin operations — time-based one-time passwords.

Protects sensitive wallet operations with a second factor.
Compatible with any TOTP authenticator app (Google Authenticator,
Authy, 1Password, Bitwarden, etc.).

Trust: Even if someone steals your API key, they can't perform
admin operations without the current TOTP code from your phone.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import sqlite3
import struct
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .config import cfg

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("wp.totp")

TOTP_INTERVAL = 30  # seconds
TOTP_DIGITS = 6
TOTP_WINDOW = 1  # +/- this many intervals


@dataclass
class TOTPConfig:
    enabled: bool
    secret: str
    created_at: float
    label: str = "walletpress-admin"


class TOTPManager:
    """Manages TOTP 2FA for admin operations."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS totp (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                enabled INTEGER DEFAULT 0,
                secret TEXT NOT NULL,
                label TEXT DEFAULT 'walletpress-admin',
                created_at REAL NOT NULL,
                last_verified_at REAL DEFAULT 0
            );
        """)
        conn.commit()
        conn.close()

    def setup(self) -> dict:
        """Generate a new TOTP secret and return provisioning data.

        Returns:
            Dict with secret, qr_uri, and manual_entry_key.
        """
        raw_secret = secrets.token_bytes(20)
        secret_b32 = base64.b32encode(raw_secret).decode().rstrip("=")

        conn = self._conn()
        exists = conn.execute("SELECT id FROM totp WHERE id = 1").fetchone()
        if exists:
            conn.execute(
                "UPDATE totp SET secret = ?, enabled = 0, created_at = ? WHERE id = 1",
                (secret_b32, time.time()),
            )
        else:
            conn.execute(
                "INSERT INTO totp (id, enabled, secret, created_at) VALUES (1, 0, ?, ?)",
                (secret_b32, time.time()),
            )
        conn.commit()
        conn.close()

        label = "WalletPress:admin"
        issuer = "WalletPress"
        qr_uri = f"otpauth://totp/{issuer}:{label}?secret={secret_b32}&issuer={issuer}&digits={TOTP_DIGITS}&period={TOTP_INTERVAL}"

        return {
            "secret_b32": secret_b32,
            "qr_uri": qr_uri,
            "manual_entry_key": secret_b32,
            "setup_complete": False,
        }

    def enable(self) -> bool:
        """Enable 2FA after setup."""
        conn = self._conn()
        conn.execute("UPDATE totp SET enabled = 1 WHERE id = 1")
        conn.commit()
        conn.close()
        return True

    def disable(self) -> bool:
        """Disable 2FA."""
        conn = self._conn()
        conn.execute("UPDATE totp SET enabled = 0 WHERE id = 1")
        conn.commit()
        conn.close()
        return True

    def is_enabled(self) -> bool:
        conn = self._conn()
        row = conn.execute("SELECT enabled FROM totp WHERE id = 1").fetchone()
        conn.close()
        return bool(row and row["enabled"])

    def _hotp(self, secret_bytes: bytes, counter: int) -> str:
        """Generate HMAC-based one-time password (RFC 4226)."""
        msg = struct.pack(">Q", counter)
        h = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
        offset = h[-1] & 0xF
        code = (struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**TOTP_DIGITS)
        return str(code).zfill(TOTP_DIGITS)

    def _totp_at_time(self, secret_bytes: bytes, timestamp: float) -> str:
        """Generate TOTP code for a specific timestamp."""
        counter = int(timestamp) // TOTP_INTERVAL
        return self._hotp(secret_bytes, counter)

    def verify(self, code: str) -> bool:
        """Verify a TOTP code within the allowed time window."""
        if not self.is_enabled():
            return True

        conn = self._conn()
        row = conn.execute("SELECT secret FROM totp WHERE id = 1").fetchone()
        conn.close()
        if not row:
            return False

        try:
            padding = 8 - (len(row["secret"]) % 8) if len(row["secret"]) % 8 else 0
            secret_bytes = base64.b32decode(row["secret"] + "=" * padding)
        except Exception as e:
            logger.error(f"TOTP decode failed: {e}")
            return False

        now = time.time()
        for offset in range(-TOTP_WINDOW, TOTP_WINDOW + 1):
            expected = self._totp_at_time(secret_bytes, now + offset * TOTP_INTERVAL)
            if hmac.compare_digest(code.strip(), expected):
                return True

        return False


_manager: TOTPManager | None = None


def get_totp_manager() -> TOTPManager:
    global _manager
    if _manager is None:
        _manager = TOTPManager(cfg.data_dir / "totp.db")
    return _manager
