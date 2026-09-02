"""Agent Safety — Central safety system for the AI Wallet Agent.

Implements in one module:
  1. HITL (Human-in-the-Loop) — confirmation queue for WRITE actions
  3. Spending limits — per-chain, per-period counters
  4. Address book — allowlist + bundled scam blocklist
  5. Permission tiers — read → plan → exec
  6. Kill switch — emergency pause
  7. Audit trail — SHA-256 chained, append-only log

All tools check safety() before executing. WRITE tools go through confirm().
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from core.config import cfg

logger = logging.getLogger("wp.agent.safety")

# ── Authenticated Actor Context ────────────────────────────────────────────────
# The HTTP auth layer (main.py) sets the authenticated actor (admin key holder)
# before dispatching into the MCP server. asyncio propagates the ContextVar to
# the SSE session task, so every tool call made by the same MCP session sees the
# same actor. HITL confirmations are bound to this actor: only the actor that
# requested a confirmation may approve it.
_actor_ctx: ContextVar[str] = ContextVar("wp_agent_actor", default="")


def set_actor(actor: str) -> None:
    """Record the authenticated actor for the current context."""
    _actor_ctx.set(actor)


def get_actor() -> str:
    """Return the authenticated actor for the current context ('' = unauthenticated)."""
    return _actor_ctx.get()


SAFETY_DB = cfg.data_dir / "agent_safety.db"


# ── Audit Entry ──────────────────────────────────────────────────────────────
@dataclass
class AuditEntry:
    id: str
    timestamp: float
    agent_tier: str
    action: str
    params: str
    result: str
    confirmed_by: str
    hash: str
    prev_hash: str
    chain: str = "local"


# ── Pending Confirmation (SQLite-backed) ──────────────────────────────────────
_pending_lock = threading.Lock()


_hitl_pool: Any = None


def _get_hitl_db():
    global _hitl_pool
    if _hitl_pool is None:
        from core.wallet_db_pool import DbPool

        _hitl_pool = DbPool(cfg.data_dir / "agent_safety.db")
        _hitl_pool.executescript("""
            CREATE TABLE IF NOT EXISTS hitl_confirmations (
                id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                params TEXT NOT NULL,
                reason TEXT DEFAULT '',
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                confirmed_by TEXT DEFAULT '',
                requested_by TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_confirmations(status);
        """)
        # Migration: older databases lack the requested_by column.
        cols = [
            r[1] for r in _hitl_pool.execute("PRAGMA table_info(hitl_confirmations)").fetchall()
        ]
        if "requested_by" not in cols:
            _hitl_pool.execute(
                "ALTER TABLE hitl_confirmations ADD COLUMN requested_by TEXT DEFAULT ''"
            )
    return _hitl_pool


# ═══════════════════════════════════════════════════════════════════════════════
#  1. HITL — Human-in-the-Loop
# ═══════════════════════════════════════════════════════════════════════════════


def request_confirmation(
    action: str, params: dict, reason: str = "", ttl: int = 900, requested_by: str = ""
) -> dict:
    """Request human confirmation for a WRITE action.

    Persisted to SQLite — survives server restarts.

    SECURITY: the requesting actor is bound to the confirmation. If the
    request is made by an authenticated actor (admin key holder), only the
    SAME actor may approve it via confirm_action(). This prevents a caller
    from self-approving a pending wallet-draining action.
    """
    if not requested_by:
        requested_by = get_actor()
    conf_id = f"conf_{secrets.token_hex(8)}"
    now = time.time()
    entry = {
        "id": conf_id,
        "action": action,
        "params": json.dumps(params),
        "reason": reason,
        "created_at": now,
        "expires_at": now + ttl,
        "status": "pending",
        "confirmed_by": "",
        "requested_by": requested_by,
    }
    with _pending_lock:
        pool = _get_hitl_db()
        pool.execute(
            "INSERT INTO hitl_confirmations (id, action, params, reason, created_at, expires_at, status, confirmed_by, requested_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry["id"],
                entry["action"],
                entry["params"],
                entry["reason"],
                entry["created_at"],
                entry["expires_at"],
                entry["status"],
                entry["confirmed_by"],
                entry["requested_by"],
            ),
        )
    logger.info(f"HITL: Confirmation requested {conf_id} for {action}")
    return {
        "confirmation_id": conf_id,
        "status": "pending",
        "expires_at": entry["expires_at"],
        "reason": reason,
        "ttl_seconds": ttl,
    }


def confirm_action(confirmation_id: str, confirmed_by: str = "human") -> dict:
    """Confirm a pending action. Returns the stored params for execution.

    SECURITY: if the confirmation was requested by an authenticated actor
    (requested_by is set), confirmations from any OTHER actor are rejected.
    Only the admin key that initiated the action may confirm it.
    """
    with _pending_lock:
        pool = _get_hitl_db()
        row = pool.execute(
            "SELECT * FROM hitl_confirmations WHERE id = ?", (confirmation_id,)
        ).fetchone()
        if not row:
            return {"error": f"Confirmation {confirmation_id} not found"}
        if row["status"] != "pending":
            return {"error": f"Confirmation already {row['status']}"}
        if row["expires_at"] < time.time():
            pool.execute(
                "UPDATE hitl_confirmations SET status = 'expired' WHERE id = ?", (confirmation_id,)
            )
            return {"error": "Confirmation expired"}
        # Actor binding: a confirmation created by an authenticated actor can
        # only be approved by the SAME actor. This closes the self-approval
        # bypass where any caller could confirm (and thus execute) a pending
        # wallet-draining action.
        requested_by = row["requested_by"] or ""
        if requested_by and confirmed_by != requested_by:
            logger.warning(
                "HITL: Confirmation %s requested by %r but confirmed by %r — denied",
                confirmation_id,
                requested_by,
                confirmed_by,
            )
            return {
                "error": (
                    "Confirmation was requested by a different actor. Only the "
                    "admin key that initiated the action may confirm it."
                )
            }
        pool.execute(
            "UPDATE hitl_confirmations SET status = 'approved', confirmed_by = ? WHERE id = ?",
            (confirmed_by, confirmation_id),
        )
        params = json.loads(row["params"])
        logger.info(f"HITL: Confirmed {confirmation_id} by {confirmed_by}")
        return {"approved": True, "params": params, "action": row["action"]}


def reject_action(confirmation_id: str, reason: str = "") -> dict:
    """Reject a pending action."""
    with _pending_lock:
        pool = _get_hitl_db()
        row = pool.execute(
            "SELECT * FROM hitl_confirmations WHERE id = ?", (confirmation_id,)
        ).fetchone()
        if not row:
            return {"error": f"Confirmation {confirmation_id} not found"}
        pool.execute(
            "UPDATE hitl_confirmations SET status = 'rejected' WHERE id = ?", (confirmation_id,)
        )
        logger.info(f"HITL: Rejected {confirmation_id}: {reason}")
        return {"rejected": True, "reason": reason, "confirmation_id": confirmation_id}


def list_pending() -> list[dict]:
    """List all pending (unexpired) confirmation requests."""
    now = time.time()
    pool = _get_hitl_db()
    rows = pool.execute(
        "SELECT * FROM hitl_confirmations WHERE status = 'pending' AND expires_at > ? ORDER BY created_at",
        (now,),
    ).fetchall()
    return [
        {
            "confirmation_id": r["id"],
            "action": r["action"],
            "reason": r["reason"],
            "expires_in": int(r["expires_at"] - now),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  5. Permission Tiers
# ═══════════════════════════════════════════════════════════════════════════════

WRITE_ACTIONS = {
    "wallet_generate",
    "wallet_from_mnemonic",
    "vault_delete",
    "wallet_rotate",
    "wallet_sweep",
    "schedule_dca",
    "schedule_remove",
    "anomaly_monitor",
    "proof_commit_pending",
    "key_export",  # Private key export — HITL required
}

PLAN_ACTIONS = {
    "agent_plan",
    "agent_execute",
}


def get_tier() -> str:
    """Get the current agent permission tier: read, plan, or exec.

    Default: 'exec' with HITL — most secure. All WRITE actions require human confirmation.
    Set WP_AGENT_TIER=plan to allow autonomous planning.
    Set WP_AGENT_TIER=read to restrict to read-only.
    """
    return os.getenv("WP_AGENT_TIER", "exec").lower()


def check_action_allowed(action: str) -> tuple[bool, str]:
    """Check if the current tier allows this action.

    Tiers:
      read  — read-only (list, balance, stats)
      plan  — read + plan but NOT execute WRITE actions
      exec  — full access (with HITL on WRITE)

    Returns (allowed: bool, reason: str).
    """
    tier = get_tier()
    is_write = action in WRITE_ACTIONS
    is_plan = action in PLAN_ACTIONS

    if tier == "exec":
        return True, ""
    if tier == "plan":
        if is_write:
            return (
                False,
                f"WRITE action '{action}' not allowed on tier 'plan'. Upgrade to 'exec' or use HITL flow.",
            )
        return True, ""  # read + plan allowed
    if tier == "read":
        if is_write or is_plan:
            return (
                False,
                f"Action '{action}' not allowed on tier 'read'. Upgrade to 'plan' or 'exec'.",
            )
        return True, ""  # read only
    return False, f"Unknown tier '{tier}'. Set WP_AGENT_TIER to read, plan, or exec."


def is_write_action(action: str) -> bool:
    """Check if an action is a WRITE (destructive/mutating) action."""
    return action in WRITE_ACTIONS


# ═══════════════════════════════════════════════════════════════════════════════
#  6. Kill Switch
# ═══════════════════════════════════════════════════════════════════════════════

KILL_FILE = cfg.data_dir / ".agent_killed"
KILL_KEY_FILE = cfg.data_dir / ".agent_kill_key"


def is_killed() -> bool:
    """Check if the agent has been killed (emergency stopped)."""
    return KILL_FILE.exists()


def kill_agent(reason: str = "") -> dict:
    """Emergency stop the agent. Returns a resurrection key."""
    KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
    KILL_FILE.write_text(
        json.dumps(
            {
                "killed_at": time.time(),
                "reason": reason or "no reason given",
            }
        )
    )
    # Generate resurrection key
    key = f"resurrect_{secrets.token_hex(16)}"
    KILL_KEY_FILE.write_text(key)
    logger.warning(f"AGENT KILLED: {reason}")
    return {
        "killed": True,
        "reason": reason,
        "killed_at": time.time(),
        "resurrection_key": key,
        "note": "Save this key to resurrect the agent.",
    }


def resurrect_agent(key: str) -> dict:
    """Resurrect a killed agent. Must provide the key from kill_agent()."""
    if not is_killed():
        return {"error": "Agent is not killed"}
    if not KILL_KEY_FILE.exists():
        return {"error": "No kill key file found. Manual override required."}
    stored_key = KILL_KEY_FILE.read_text().strip()
    if not hmac.compare_digest(key, stored_key):
        return {"error": "Invalid resurrection key"}
    KILL_FILE.unlink(missing_ok=True)
    KILL_KEY_FILE.unlink(missing_ok=True)
    logger.info("AGENT RESURRECTED")
    return {"resurrected": True}


# ═══════════════════════════════════════════════════════════════════════════════
#  3. Spending Limits
# ═══════════════════════════════════════════════════════════════════════════════

_LIMITS_DB_LOCK = threading.Lock()


def _get_limits_db() -> sqlite3.Connection:
    SAFETY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SAFETY_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spending_limits (
            chain TEXT NOT NULL,
            period TEXT NOT NULL,
            max_amount REAL NOT NULL,
            PRIMARY KEY (chain, period)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spending_usage (
            chain TEXT NOT NULL,
            period TEXT NOT NULL,
            window_start REAL NOT NULL,
            amount_used REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (chain, period, window_start)
        )
    """)
    conn.commit()
    return conn


def _period_start(period: str) -> float:
    """Get the unix timestamp for the start of the current period.

    daily: start of current UTC day
    weekly: start of current UTC week (Monday)
    monthly: start of current UTC month
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        # Monday of current week
        days_since_monday = now.weekday()
        start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif period == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return time.time()
    return start.timestamp()


def _get_usage(chain: str, period: str) -> float:
    """Get the current usage for a chain+period."""
    window_start = _period_start(period)
    conn = _get_limits_db()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_used), 0) FROM spending_usage "
        "WHERE chain = ? AND period = ? AND window_start = ?",
        (chain, period, window_start),
    ).fetchone()
    conn.close()
    return float(row[0]) if row and row[0] else 0.0


def check_spending_limit(chain: str, amount: float) -> dict:
    """Check if an action would exceed spending limits.

    Config via env vars:
      WP_AGENT_LIMIT_{CHAIN}_DAILY=<max>
      WP_AGENT_LIMIT_{CHAIN}_WEEKLY=<max>
      WP_AGENT_LIMIT_{CHAIN}_MONTHLY=<max>

    Returns dict with allowed, limits, usage.
    """
    env_prefix = f"WP_AGENT_LIMIT_{chain.upper()}"
    limits = {}
    for period in ["daily", "weekly", "monthly"]:
        max_amt = os.getenv(f"{env_prefix}_{period.upper()}")
        if max_amt:
            limit = float(max_amt)
            used = _get_usage(chain, period)
            limits[period] = {"limit": limit, "used": used, "remaining": max(0, limit - used)}

    if not limits:
        return {"allowed": True, "limits": {}, "note": "No limits configured"}

    # Check all limits
    exceeded = []
    for period, info in limits.items():
        if info["used"] + amount > info["limit"]:
            exceeded.append(
                f"{period}: {info['used'] + amount:.4f} exceeds limit of {info['limit']:.4f} "
                f"(used {info['used']:.4f} + proposed {amount:.4f})"
            )

    if exceeded:
        return {"allowed": False, "limits": limits, "exceeded": exceeded}

    return {"allowed": True, "limits": limits, "note": "All limits satisfied"}


def record_spending(chain: str, amount: float):
    """Record spending usage after an action executes.

    Uses atomic UPDATE to avoid race conditions under concurrent access.
    """
    with _LIMITS_DB_LOCK:
        conn = _get_limits_db()
        for period in ["daily", "weekly", "monthly"]:
            ws = _period_start(period)
            conn.execute(
                "INSERT INTO spending_usage (chain, period, window_start, amount_used) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(chain, period, window_start) "
                "DO UPDATE SET amount_used = amount_used + ?",
                (chain, period, ws, amount, amount),
            )
        conn.commit()
        conn.close()


def list_limits() -> dict:
    """Show all configured spending limits with current usage."""
    conn = _get_limits_db()
    rows = conn.execute("SELECT * FROM spending_usage ORDER BY chain, period").fetchall()
    conn.close()
    # Aggregate by chain + period
    usage: dict[str, dict[str, float]] = {}
    for r in rows:
        usage.setdefault(r["chain"], {}).setdefault(r["period"], 0.0)
        usage[r["chain"]][r["period"]] += r["amount_used"]
    return {"usage": usage}


# ═══════════════════════════════════════════════════════════════════════════════
#  4. Address Book (Allowlist + Blocklist + Scam DB)
# ═══════════════════════════════════════════════════════════════════════════════


def _get_addr_db() -> sqlite3.Connection:
    SAFETY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SAFETY_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS address_book (
            address TEXT NOT NULL,
            chain TEXT NOT NULL,
            label TEXT DEFAULT '',
            list_type TEXT NOT NULL DEFAULT 'allowlist',
            added_at REAL NOT NULL,
            PRIMARY KEY (address, chain)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_addr_list ON address_book(list_type)
    """)
    conn.commit()
    return conn


def allowlist_add(address: str, chain: str, label: str = "") -> dict:
    """Add an address to the allowlist."""
    conn = _get_addr_db()
    conn.execute(
        "INSERT OR REPLACE INTO address_book (address, chain, label, list_type, added_at) "
        "VALUES (?, ?, ?, 'allowlist', ?)",
        (address.lower(), chain.lower(), label, time.time()),
    )
    conn.commit()
    conn.close()
    return {"added": True, "address": address, "chain": chain, "label": label, "list": "allowlist"}


def blocklist_add(address: str, chain: str, label: str = "") -> dict:
    """Add an address to the blocklist."""
    conn = _get_addr_db()
    conn.execute(
        "INSERT OR REPLACE INTO address_book (address, chain, label, list_type, added_at) "
        "VALUES (?, ?, ?, 'blocklist', ?)",
        (address.lower(), chain.lower(), label, time.time()),
    )
    conn.commit()
    conn.close()
    return {"added": True, "address": address, "chain": chain, "list": "blocklist"}


def address_book_list(list_type: str = "") -> list[dict]:
    """List addresses in the address book. Filter by list_type: allowlist, blocklist, or '' for all."""
    conn = _get_addr_db()
    if list_type:
        rows = conn.execute(
            "SELECT * FROM address_book WHERE list_type = ? ORDER BY added_at DESC",
            (list_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM address_book ORDER BY list_type, added_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def address_book_remove(address: str, chain: str) -> dict:
    """Remove an address from the address book."""
    conn = _get_addr_db()
    conn.execute(
        "DELETE FROM address_book WHERE address = ? AND chain = ?", (address.lower(), chain.lower())
    )
    conn.commit()
    removed = conn.total_changes > 0
    conn.close()
    return {"removed": removed}


def check_address(address: str, chain: str) -> dict:
    """Check if a destination address is safe to send to.

    Returns:
        allowed: True if address is allowed
        reason: Why it was blocked/allowed
        lists: Which lists the address appears in
    """
    addr_lower = address.lower()
    chain_lower = chain.lower()
    conn = _get_addr_db()

    # Check blocklist first
    blocked = conn.execute(
        "SELECT * FROM address_book WHERE address = ? AND chain = ? AND list_type = 'blocklist'",
        (addr_lower, chain_lower),
    ).fetchone()
    if blocked:
        conn.close()
        return {
            "allowed": False,
            "reason": f"Address is on blocklist: {blocked['label']}",
            "lists": ["blocklist"],
        }

    # Check against bundled scam DB (if loaded)
    scam_check = _check_scam_db(addr_lower, chain_lower)
    if scam_check:
        conn.close()
        return {
            "allowed": False,
            "reason": f"Address is a known scam address: {scam_check}",
            "lists": ["scam_db"],
        }

    # Check allowlist (if configured to require allowlist)
    require_allowlist = os.getenv("WP_AGENT_REQUIRE_ALLOWLIST", "0") == "1"
    if require_allowlist:
        allowed = conn.execute(
            "SELECT * FROM address_book WHERE address = ? AND chain = ? AND list_type = 'allowlist'",
            (addr_lower, chain_lower),
        ).fetchone()
        conn.close()
        if not allowed:
            return {
                "allowed": False,
                "reason": "Address not in allowlist (WP_AGENT_REQUIRE_ALLOWLIST=1)",
                "lists": [],
            }
    conn.close()
    return {"allowed": True, "reason": "Address is safe", "lists": []}


# ── Bundled Scam DB ──────────────────────────────────────────────────────────
# Compressed list of known scam addresses. Updated via make update-scam-db.
_SCAM_DB: dict[str, set[str]] = {"eth": set(), "sol": set(), "bsc": set()}
_SCAM_DB_LOADED = False
_SCAM_DB_LOCK = threading.Lock()


def _load_scam_db():
    global _SCAM_DB_LOADED
    with _SCAM_DB_LOCK:
        if _SCAM_DB_LOADED:
            return
        db_path = cfg.data_dir / "scam_addresses.json"
        if db_path.exists():
            try:
                data = json.loads(db_path.read_text())
                for chain, addrs in data.items():
                    _SCAM_DB[chain.lower()] = {a.lower() for a in addrs}
                logger.info(f"Loaded {sum(len(v) for v in _SCAM_DB.values())} scam addresses")
            except Exception as e:
                logger.warning(f"Failed to load scam DB: {e}")
        _SCAM_DB_LOADED = True


def _check_scam_db(address: str, chain: str) -> str:
    """Check bundled scam DB. Returns label if found, empty string if safe."""
    if not _SCAM_DB_LOADED:
        _load_scam_db()
    chain_addrs = _SCAM_DB.get(chain, set())
    if address in chain_addrs:
        return "Known malicious address"
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
#  7. Audit Trail — SHA-256 chained
# ═══════════════════════════════════════════════════════════════════════════════


def _get_audit_db() -> sqlite3.Connection:
    SAFETY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SAFETY_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_audit (
            id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            agent_tier TEXT NOT NULL,
            action TEXT NOT NULL,
            params TEXT NOT NULL,
            result TEXT NOT NULL,
            confirmed_by TEXT DEFAULT '',
            hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL DEFAULT '',
            chain TEXT DEFAULT 'local'
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_time ON agent_audit(timestamp)
    """)
    conn.commit()
    return conn


def _get_last_audit_hash(conn: sqlite3.Connection) -> str:
    """Get the hash of the most recent audit entry."""
    row = conn.execute("SELECT hash FROM agent_audit ORDER BY rowid DESC LIMIT 1").fetchone()
    return row[0] if row else "0" * 64


def audit_log(action: str, params: dict, result: Any, confirmed_by: str = "", chain: str = "local"):
    """Append an entry to the audit trail. SHA-256 chained to previous entry.

    The chain is: prev_hash = sha256(prev_entry), current_hash = sha256(prev_hash + current_data).
    This makes the log tamper-evident: any modification breaks the chain.
    """
    entry_id = f"audit_{int(time.time() * 1000000)}_{secrets.token_hex(4)}"
    now = time.time()
    tier = get_tier()
    params_json = json.dumps(params, default=str, sort_keys=True)
    result_json = json.dumps(result, default=str, sort_keys=True)

    conn = _get_audit_db()
    prev_hash = _get_last_audit_hash(conn)
    current_hash = hashlib.sha256(
        (prev_hash + entry_id + str(now) + action + params_json + result_json).encode()
    ).hexdigest()

    conn.execute(
        """INSERT INTO agent_audit
        (id, timestamp, agent_tier, action, params, result, confirmed_by, hash, prev_hash, chain)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entry_id,
            now,
            tier,
            action,
            params_json,
            result_json,
            confirmed_by,
            current_hash,
            prev_hash,
            chain,
        ),
    )
    conn.commit()
    conn.close()
    logger.debug(f"Audit: {entry_id} — {action}")


def audit_trail(limit: int = 50) -> list[dict]:
    """Get the most recent audit trail entries (newest first)."""
    conn = _get_audit_db()
    rows = conn.execute(
        "SELECT * FROM agent_audit ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        entry = dict(r)
        entry["params"] = (
            json.loads(entry["params"]) if isinstance(entry["params"], str) else entry["params"]
        )
        entry["result"] = (
            json.loads(entry["result"]) if isinstance(entry["result"], str) else entry["result"]
        )
        result.append(entry)
    return result


def verify_audit_chain() -> dict:
    """Verify the integrity of the entire audit trail.

    Recomputes all hashes and checks that each entry's hash matches,
    and that each entry's prev_hash matches the previous entry's hash.
    """
    conn = _get_audit_db()
    rows = conn.execute("SELECT * FROM agent_audit ORDER BY timestamp ASC").fetchall()
    conn.close()
    issues = []
    prev_hash = "0" * 64
    for r in rows:
        expected_hash = hashlib.sha256(
            (
                prev_hash + r["id"] + str(r["timestamp"]) + r["action"] + r["params"] + r["result"]
            ).encode()
        ).hexdigest()
        if not hmac.compare_digest(r["hash"], expected_hash):
            issues.append(f"Hash mismatch at {r['id']}")
        if not hmac.compare_digest(r["prev_hash"], prev_hash):
            issues.append(
                f"Chain broken at {r['id']}: expected prev_hash={prev_hash}, got {r['prev_hash']}"
            )
        prev_hash = r["hash"]
    if issues:
        return {"valid": False, "issues": issues, "entries_checked": len(rows)}
    return {"valid": True, "entries_checked": len(rows)}


# ═══════════════════════════════════════════════════════════════════════════════
#  2. Transaction Simulation (lightweight)
# ═══════════════════════════════════════════════════════════════════════════════


async def simulate_transaction(
    chain: str, from_address: str, to_address: str, amount: float
) -> dict:
    """Simulate a transaction without broadcasting (async — P2-6 fix).

    For EVM chains: uses eth_estimateGas + eth_gasPrice to project total cost.
    For Solana: stub (use simulateTransaction via Solana RPC if added).
    Falls back to a best-effort estimate if RPC unavailable.

    This is async because it's called from inside an MCP tool handler that
    is already inside a running event loop. The previous sync version used
    asyncio.run() which raises "asyncio.run() cannot be called from a running
    event loop" in that context.
    """
    import httpx

    from routers.balance_fetcher import EVM_RPC

    if chain in EVM_RPC:
        rpc_url = EVM_RPC[chain]
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                gas_est = await c.post(
                    rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_estimateGas",
                        "params": [
                            {
                                "from": from_address,
                                "to": to_address,
                                "value": hex(int(amount * 1e18)),
                            }
                        ],
                        "id": 1,
                    },
                )
                gas_data = gas_est.json()
                gas = int(gas_data.get("result", "0x5208"), 16) if "result" in gas_data else 21000

                price = await c.post(
                    rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_gasPrice",
                        "params": [],
                        "id": 1,
                    },
                )
                price_data = price.json()
                gas_price = (
                    int(price_data.get("result", "0x3b9aca00"), 16)
                    if "result" in price_data
                    else int(1e9)
                )

                gas_cost_eth = (gas * gas_price) / 1e18
                return {
                    "simulated": True,
                    "chain": chain,
                    "from": from_address,
                    "to": to_address,
                    "amount": amount,
                    "gas_estimate": gas,
                    "gas_price_gwei": gas_price / 1e9,
                    "gas_cost_eth": round(gas_cost_eth, 8),
                    "total_cost_eth": round(amount + gas_cost_eth, 8),
                    "status": "likely_success",
                }
        except Exception as e:
            logger.debug(f"Simulation failed for {chain}: {e}")

    return {
        "simulated": False,
        "chain": chain,
        "from": from_address,
        "to": to_address,
        "amount": amount,
        "gas_estimate": "unknown (non-EVM chain or RPC unreachable)",
        "note": "Full simulation requires chain-specific RPC. Showing intended params.",
    }
