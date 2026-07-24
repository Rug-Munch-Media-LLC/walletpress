"""WalletPress Hosted — multi-tenant user management + usage tracking.

Revenue model:
  Free:    3 chains, 10 wallets/day, no API access
  Starter: $29/mo, 10 chains, 500 wallets/day, API access
  Pro:     $79/mo, 55 chains, unlimited wallets, full API, 2FA
  Enterprise: $199/mo, everything + dedicated support + SLA

Users self-register, get API keys, and pay via Stripe.
Admin creates plans, views usage, manages subscriptions.

SECURITY: Passwords are hashed with Argon2id (m=64MB, t=3, p=4).
Legacy SHA-256 hashes are migrated on next successful login.
"""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import (
    VerifyMismatchError,
    InvalidHashError,
    VerificationError,
)

from .config import cfg

logger = logging.getLogger("wp.hosting")

# Argon2id parameters: OWASP recommendations as of 2024
# m = 64 MiB memory cost, t = 3 iterations, p = 4 parallelism
# (argon2-cffi defaults are 64MB / 3 iterations / 4 lanes)
_ph = PasswordHasher()


def _hash_password(plaintext: str) -> str:
    """Hash a password with Argon2id. Returns the encoded hash string.

    The returned string includes the salt, parameters, and hash in a
    self-describing format like:
        $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>
    """
    return _ph.hash(plaintext)


def _verify_password(stored_hash: str, plaintext: str) -> bool:
    """Verify a plaintext password against a stored hash.

    Supports both new Argon2id hashes AND legacy unsalted SHA-256 hashes
    (for migration). Returns True on match, False on mismatch.
    """
    if not stored_hash:
        return False
    # Legacy SHA-256 hash: 64 hex chars, no $ separators
    if "$" not in stored_hash and len(stored_hash) == 64:
        try:
            import hashlib

            legacy_match = hashlib.sha256(plaintext.encode()).hexdigest() == stored_hash
            return legacy_match
        except Exception:
            return False
    # Argon2id hash
    try:
        _ph.verify(stored_hash, plaintext)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _needs_rehash(stored_hash: str) -> bool:
    """Check if the stored hash uses outdated parameters and needs re-hashing."""
    if "$" not in stored_hash:
        return True  # Legacy SHA-256 — needs migration to Argon2id
    try:
        return _ph.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


PLANS = {
    "free": {
        "name": "Free",
        "price_usd": 0,
        "chains": 3,
        "daily_wallet_limit": 10,
        "api_access": False,
        "features": ["basic_generation"],
    },
    "starter": {
        "name": "Starter",
        "price_usd": 29,
        "chains": 10,
        "daily_wallet_limit": 500,
        "api_access": True,
        "features": ["basic_generation", "batch", "mnemonic", "export"],
    },
    "pro": {
        "name": "Pro",
        "price_usd": 79,
        "chains": 55,
        "daily_wallet_limit": 0,
        "api_access": True,
        "features": ["all"],
    },
    "enterprise": {
        "name": "Enterprise",
        "price_usd": 199,
        "chains": 55,
        "daily_wallet_limit": 0,
        "api_access": True,
        "features": ["all", "2fa", "sla"],
    },
}


def _check_legacy_hashes() -> None:
    """Scan all users for legacy SHA-256 hashes on startup. Log WARNING for each."""
    try:
        from .config import cfg

        db_path = cfg.data_dir / "hosting.db"
        if not db_path.exists():
            return
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, email FROM users").fetchall()
        conn.close()
        legacy = [r for r in rows if r["email"] and "$" not in r.get("password_hash", "")]
        if legacy:
            logger.warning(
                f"FOUND {len(legacy)} USER(S) WITH LEGACY SHA-256 HASHES — they will be forced to reset on next login"
            )
            for r in legacy:
                logger.warning(f"  User {r['id']} ({r['email']}) has SHA-256 hash")
        else:
            logger.info("All user password hashes are Argon2id — no migration needed")
    except Exception as e:
        logger.warning(f"Legacy hash check failed: {e}")


class HostingDB:
    """User and subscription management."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT DEFAULT '',
                plan TEXT DEFAULT 'free',
                api_key TEXT UNIQUE DEFAULT '',
                stripe_customer_id TEXT DEFAULT '',
                subscription_id TEXT DEFAULT '',
                subscription_status TEXT DEFAULT 'active',
                created_at REAL NOT NULL,
                last_login_at REAL DEFAULT 0,
                email_verified INTEGER DEFAULT 0,
                email_verify_token TEXT DEFAULT '',
                email_verify_expires REAL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                chain TEXT DEFAULT '',
                count INTEGER DEFAULT 1,
                timestamp REAL NOT NULL,
                ip TEXT DEFAULT '',
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_usage_date ON usage_log(timestamp);
        """)
        conn.commit()
        conn.close()

    def register(self, email: str, password: str, name: str = "") -> dict:
        """Register a new user with email verification (P2-12 fix).

        Email verification is OPT-IN via WP_REQUIRE_EMAIL_VERIFY=1. By default
        (community / self-hosted dev), users can use the API key immediately.
        For hosted deployments with SMTP configured, set that flag to require
        email confirmation before the API key becomes active.

        Returns:
            dict with user_id, api_key (provisional), plan, and optionally
            a verification_token the caller should email to the user.
        """
        conn = self._conn()
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.close()
            return {"error": "Email already registered"}
        user_id = f"u_{secrets.token_hex(8)}"
        pw_hash = _hash_password(password)
        api_key = f"wp_live_{secrets.token_hex(24)}"
        require_verify = os.getenv("WP_REQUIRE_EMAIL_VERIFY", "0") == "1"
        verify_token = secrets.token_urlsafe(32) if require_verify else ""
        verify_expires = time.time() + 86400 if require_verify else 0  # 24h
        conn.execute(
            """INSERT INTO users
               (id, email, password_hash, name, plan, api_key, created_at,
                email_verified, email_verify_token, email_verify_expires)
               VALUES (?, ?, ?, ?, 'free', ?, ?, ?, ?, ?)""",
            (
                user_id,
                email,
                pw_hash,
                name,
                api_key,
                time.time(),
                0 if require_verify else 1,  # auto-verify if not required
                verify_token,
                verify_expires,
            ),
        )
        conn.commit()
        conn.close()
        result = {
            "user_id": user_id,
            "api_key": api_key,
            "plan": "free",
            "email_verification_required": require_verify,
        }
        if require_verify:
            result["verification_token"] = verify_token
            result["note"] = (
                "Send POST /hosting/verify-email with {token} to activate. "
                "Token expires in 24h. Configure WP_SMTP_HOST etc. to send "
                "the email automatically (see core/email_notify.py)."
            )
        return result

    def verify_email(self, token: str) -> bool:
        """Mark the email as verified using a token from registration."""
        if not token:
            return False
        conn = self._conn()
        row = conn.execute(
            "SELECT id, email_verify_expires FROM users WHERE email_verify_token = ?",
            (token,),
        ).fetchone()
        if not row:
            conn.close()
            return False
        if row["email_verify_expires"] and time.time() > row["email_verify_expires"]:
            conn.close()
            return False
        conn.execute(
            """UPDATE users
               SET email_verified = 1, email_verify_token = '', email_verify_expires = 0
               WHERE id = ?""",
            (row["id"],),
        )
        conn.commit()
        conn.close()
        return True

    def is_email_verified(self, user_id: str) -> bool:
        """True if the user has verified their email (or verification is not required)."""
        conn = self._conn()
        row = conn.execute("SELECT email_verified FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        if not row:
            return False
        return bool(row["email_verified"])

    def login(self, email: str, password: str) -> dict | None:
        """Verify login and migrate legacy SHA-256 hash to Argon2id on success.

        Returns the user row (without password_hash) on success, None on failure.
        On successful login with an outdated hash, transparently re-hashes the
        password with current Argon2id parameters.
        """
        conn = self._conn()
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            conn.close()
            return None
        stored_hash = row["password_hash"]
        if not _verify_password(stored_hash, password):
            conn.close()
            return None

        # Migrate outdated hash to current Argon2id params
        if _needs_rehash(stored_hash):
            try:
                new_hash = _hash_password(password)
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (new_hash, row["id"]),
                )
                conn.commit()
                logger.info(f"Migrated password hash to Argon2id for user {row['id']}")
            except Exception as e:
                logger.warning(f"Password hash migration failed for user {row['id']}: {e}")

        # Return everything except password_hash — never leak it
        safe = {k: v for k, v in dict(row).items() if k != "password_hash"}
        conn.close()
        return safe

    def get_by_api_key(self, api_key: str) -> dict | None:
        conn = self._conn()
        row = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def log_usage(self, user_id: str, action: str, chain: str = "", count: int = 1, ip: str = ""):
        conn = self._conn()
        conn.execute(
            "INSERT INTO usage_log (user_id, action, chain, count, timestamp, ip) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, action, chain, count, time.time(), ip),
        )
        conn.commit()
        conn.close()

    def daily_usage(self, user_id: str) -> int:
        today = int(time.time()) - (int(time.time()) % 86400)
        conn = self._conn()
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) as total FROM usage_log WHERE user_id = ? AND timestamp >= ?",
            (user_id, today),
        ).fetchone()
        conn.close()
        return row["total"] if row else 0

    def check_limit(self, user_id: str) -> tuple[bool, str]:
        conn = self._conn()
        row = conn.execute("SELECT plan FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        if not row:
            return False, "User not found"
        plan = PLANS.get(row["plan"], PLANS["free"])
        if plan["daily_wallet_limit"] == 0:
            return True, ""  # Unlimited
        used = self.daily_usage(user_id)
        if used >= plan["daily_wallet_limit"]:
            return (
                False,
                f"Daily limit reached ({plan['daily_wallet_limit']} wallets). Upgrade at /hosting/plans",
            )
        return True, ""

    def get_user(self, user_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return dict(row) if row else None


# Singleton
_hosting: HostingDB | None = None


def get_hosting() -> HostingDB:
    global _hosting
    if _hosting is None:
        _hosting = HostingDB(cfg.data_dir / "hosting.db")
    return _hosting
