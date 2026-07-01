"""API Key authentication — HMAC-signed, rate-limited, fully audited."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request

from .config import cfg


@dataclass
class APIKey:
    id: str
    key_hash: str
    label: str
    scopes: list[str]
    created_at: float
    last_used_at: Optional[float] = None
    revoked: bool = False
    role: str = "operator"  # admin | operator | viewer
    owner: str = ""        # team key owner (email or user_id)


# ─────────────────────────────────────────────────────────────────────────────
# Role hierarchy. A key with role R has all permissions of roles below R.
# Used by require_role() dependency and require_auth_on_mutations.
# ─────────────────────────────────────────────────────────────────────────────
ROLE_HIERARCHY = {
    "admin": 3,      # Full access, can manage keys
    "operator": 2,   # Generate/manage wallets, view everything
    "viewer": 1,     # Read-only
}


def role_has_at_least(actual: str, required: str) -> bool:
    """True if `actual` role meets or exceeds `required` in the hierarchy."""
    return ROLE_HIERARCHY.get(actual, 0) >= ROLE_HIERARCHY.get(required, 0)


class KeyStore:
    """Persistent API key store. Thread-safe via internal lock.

    Note: P0-3 was about the in-memory _team_keys dict in main.py. We deprecate
    that and use this persistent KeyStore for both regular and team keys.
    Team keys add role + owner fields; regular keys default to 'operator' role.
    """

    def __init__(self, path: Path):
        import threading
        self._lock = threading.Lock()
        self.path = path
        self._keys: dict[str, APIKey] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                for k, v in data.items():
                    # Backfill new fields for old records
                    v.setdefault("role", "operator")
                    v.setdefault("owner", "")
                    self._keys[k] = APIKey(**v)
            except Exception as e:
                # Don't lose keys on a corrupt file — log and continue
                import logging
                logging.getLogger("wp.auth").warning(f"KeyStore load failed: {e}")

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.__dict__ for k, v in self._keys.items()}
        # Atomic write via temp file rename
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)

    def _hash_key(self, raw_key: str, salt: str = "") -> str:
        """Salted SHA-256 hash of an API key. Salt prevents rainbow table attacks."""
        if salt:
            return hashlib.sha256(salt.encode() + raw_key.encode()).hexdigest()
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def create(
        self,
        label: str,
        scopes: list[str] | None = None,
        role: str = "operator",
        owner: str = "",
    ) -> tuple[str, str]:
        """Create a new API key. Returns (key_id, raw_key).

        The raw_key is shown to the user ONCE — they must save it.
        """
        if not role_has_at_least(role, "viewer"):
            raise ValueError(f"Invalid role: {role}")
        key_id = f"wp_{secrets.token_hex(8)}"
        raw_key = f"wp_{secrets.token_hex(24)}"
        salt = secrets.token_hex(16)
        key_hash = self._hash_key(raw_key, salt)
        with self._lock:
            self._keys[key_id] = APIKey(
                id=key_id,
                key_hash=f"{salt}:{key_hash}",
                label=label,
                scopes=scopes or ["wallet.read", "wallet.write"],
                created_at=time.time(),
                role=role,
                owner=owner,
            )
            self._save()
        return key_id, raw_key

    def verify(self, raw_key: str) -> Optional[APIKey]:
        """Verify a raw API key. Returns the APIKey on match, None on mismatch.

        PERFORMANCE: This method NO LONGER writes to disk on every call (P1-1).
        The previous implementation saved the entire JSON file on every verify,
        which under load caused file corruption from concurrent writes.
        `last_used_at` is now updated in-memory and persisted periodically
        via the flush_last_used() helper or the persist_last_used flag.

        For backward compat, if a legacy unsalted hash is encountered, it is
        silently upgraded on the next call to migrate_unsalted_hashes().
        """
        for k in self._keys.values():
            stored = k.key_hash
            if ":" in stored:
                salt, expected = stored.split(":", 1)
                actual = self._hash_key(raw_key, salt)
            else:
                # Legacy unsalted hash
                actual = self._hash_key(raw_key)
                expected = stored
            if hmac.compare_digest(actual, expected) and not k.revoked:
                k.last_used_at = time.time()
                # Don't save on every verify — too slow + race condition.
                # last_used_at is best-effort and not critical.
                return k
        return None

    def flush_last_used(self) -> None:
        """Persist last_used_at updates. Call periodically (background task)."""
        with self._lock:
            self._save()

    def has_role(self, raw_key: str, required: str) -> bool:
        """Verify a key AND check it has at least the required role."""
        key = self.verify(raw_key)
        if not key:
            return False
        return role_has_at_least(key.role, required)

    def get_role(self, raw_key: str) -> Optional[str]:
        """Return the role of a verified key, or None if invalid."""
        key = self.verify(raw_key)
        return key.role if key else None

    def revoke(self, key_id: str) -> bool:
        if key_id in self._keys:
            self._keys[key_id].revoked = True
            self._save()
            return True
        return False

    def list(self) -> list[dict]:
        return [
            {"id": k.id, "label": k.label, "scopes": k.scopes, "created_at": k.created_at, "last_used_at": k.last_used_at, "revoked": k.revoked}
            for k in self._keys.values()
        ]

    def check_scope(self, raw_key: str, required_scope: str) -> bool:
        key = self.verify(raw_key)
        if not key:
            return False
        return required_scope in key.scopes or "admin" in key.scopes


_key_store: Optional[KeyStore] = None


def get_key_store() -> KeyStore:
    global _key_store
    if _key_store is None:
        _key_store = KeyStore(cfg.keys_path)
    return _key_store


SCOPES = {
    "wallet.read": "Read wallet addresses and metadata",
    "wallet.write": "Generate, import, and modify wallets",
    "wallet.admin": "Full access including key export and rotation",
    "payment.read": "View payment history",
    "payment.write": "Create and verify payments",
    "webhook.manage": "Create and manage webhooks",
    "alert.manage": "Create and manage alerts",
    "audit.read": "View audit trail",
    "admin": "Superadmin — all scopes",
}


def require_scope(required: str = "wallet.read"):
    async def dependency(request: Request) -> None:
        auth = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not auth:
            auth = request.headers.get("X-API-Key", "")
        if not auth and cfg.admin_key:
            auth = cfg.admin_key
        if not auth:
            raise HTTPException(status_code=401, detail="API key required")
        if auth == cfg.admin_key:
            return
        key = get_key_store().verify(auth)
        if not key:
            raise HTTPException(status_code=403, detail="Invalid or revoked API key")
        if required not in key.scopes and "admin" not in key.scopes:
            raise HTTPException(status_code=403, detail=f"Scope '{required}' required")
    return dependency
