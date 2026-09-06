"""Shared config, models, DB, and helpers for the x402 marketplace."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.config import cfg
from wallet_engine.chains import CHAINS

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("wp.x402")

router = APIRouter(prefix="/api/v1/marketplace", tags=["Marketplace"])

PRICE_PER_WALLET = 0.01
PRICE_1000 = 0.005
PRICE_10000 = 0.002
PRICE_100000 = 0.001
MIN_ORDER_USD = 1.00
FREE_WALLETS = 10

# -- Async Job Queue --
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_WARM_POOL: dict[str, list[dict[str, Any]]] = {}
_WARM_POOL_LOCK = threading.Lock()
_WARM_POOL_TARGET = 500  # keep 500 wallets warm per chain
_WARM_POOL_MIN = 100  # refill when below this
_WARM_POOL_MAX_BATCH = 200  # generate at most this many per refill cycle

# -- Per-API-key webhook configs --
_api_webhooks: dict[str, str] = {}  # api_key_prefix -> webhook_url
_api_webhooks_lock = threading.Lock()

# -- SLA tracking --
_sla_start = time.time()
_sla_generations: list[float] = []  # timestamps of last 10k generations
_sla_latencies: list[float] = []  # seconds per generation
_sla_lock = threading.Lock()

# -- Timelock state --
_timelocks: dict[str, dict[str, Any]] = {}
_timelocks_lock = threading.Lock()

# -- Free tier state --
_free_tier_buckets: dict[str, float] = {}
_free_tier_lock = threading.Lock()
_FREE_DAILY_LIMIT = 10


def calc_price(count: int) -> float:
    """Calculate the total USD price for a given wallet count using tiered pricing."""
    if count >= 100000:
        return round(count * PRICE_100000, 2)
    if count >= 10000:
        return round(count * PRICE_10000, 2)
    if count >= 1000:
        return round(count * PRICE_1000, 2)
    return round(count * PRICE_PER_WALLET, 2)


class GenerateRequest(BaseModel):
    chain: str = Field(default="sol", help="Chain key: sol, base, polygon, arbitrum, eth")
    count: int = Field(default=1, ge=1, le=100000)
    payment_tx: str = Field(default="", help="USDC tx for paid orders. Leave empty for free tier.")
    api_key: str = Field(default="", help="Prepaid API key. Alternative to per-order payment.")
    derivation_path: str = Field(
        default="",
        help="Custom BIP44 derivation path (e.g. m/44'/60'/0'/0/1). Empty = chain default.",
    )
    xpub: str = Field(
        default="",
        help="Master public key (xpub/tpub/ypub/zpub). Derive child keys without us seeing private keys.",
    )
    idempotency_key: str = Field(
        default="",
        help="Idempotency key. Same key = same order returned. Prevents double-charge on retry.",
    )


class MultiSigRequest(BaseModel):
    chain: str = Field(default="eth")
    required: int = Field(default=2, ge=1, le=10, description="Required signatures (M)")
    total_keys: int = Field(default=3, ge=1, le=10, description="Total signers (N)")
    public_keys: list[str] = Field(
        default_factory=list,
        description="Optional: provide your own public keys. Empty = we generate.",
    )


class ShardRequest(BaseModel):
    chain: str = Field(default="eth")
    total_shards: int = Field(default=5, ge=2, le=20, description="Total shards to create")
    threshold: int = Field(default=3, ge=2, le=20, description="Shards required to reconstruct")


class ExportRequest(BaseModel):
    order_id: str = Field(...)
    format: str = Field(default="json", pattern="^(json|csv|keystore|encrypted_zip)$")


class TimelockRequest(BaseModel):
    chain: str = Field(default="sol")
    count: int = Field(default=1, ge=1, le=1000)
    release_at: float = Field(..., description="Unix timestamp when keys should be released")
    auth_signature: str = Field(
        default="", description="Optional: second auth signature for release"
    )
    webhook_url: str = Field(default="", description="Webhook to POST keys to when released")


class _DB:
    """SQLite database for marketplace orders and prepaid credits."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY, chain TEXT NOT NULL,
                count INTEGER NOT NULL, amount_usd REAL NOT NULL,
                payment_tx TEXT DEFAULT '', status TEXT DEFAULT 'completed',
                created_at REAL NOT NULL, bot_ip TEXT DEFAULT '',
                idempotency_key TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_orders_idempotency ON orders(idempotency_key);
            CREATE TABLE IF NOT EXISTS credits (
                api_key TEXT PRIMARY KEY, balance REAL NOT NULL DEFAULT 0,
                total_spent REAL DEFAULT 0, created_at REAL NOT NULL
            );
        """)
        conn.commit()
        conn.close()

    def _conn(self):
        """Return a new SQLite connection with Row factory."""
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def get_balance(self, api_key: str) -> float:
        """Return the prepaid credit balance for the given API key (0 if none)."""
        conn = self._conn()
        row = conn.execute("SELECT balance FROM credits WHERE api_key = ?", (api_key,)).fetchone()
        conn.close()
        return row["balance"] if row else 0.0

    def deduct(self, api_key: str, amount: float) -> bool:
        """Deduct ``amount`` from the API key's balance. Return True on success."""
        conn = self._conn()
        row = conn.execute("SELECT balance FROM credits WHERE api_key = ?", (api_key,)).fetchone()
        if not row or row["balance"] < amount:
            conn.close()
            return False
        conn.execute(
            "UPDATE credits SET balance = balance - ?, total_spent = total_spent + ? WHERE api_key = ?",
            (amount, amount, api_key),
        )
        conn.commit()
        conn.close()
        return True

    def add_credits(self, api_key: str, amount: float):
        """Add prepaid credits to the given API key (create if new)."""
        conn = self._conn()
        existing = conn.execute(
            "SELECT api_key FROM credits WHERE api_key = ?", (api_key,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE credits SET balance = balance + ? WHERE api_key = ?", (amount, api_key)
            )
        else:
            conn.execute(
                "INSERT INTO credits (api_key, balance, total_spent, created_at) VALUES (?, ?, 0, ?)",
                (api_key, amount, time.time()),
            )
        conn.commit()
        conn.close()

    def log_order(self, order_id, chain, count, amount, payment_tx, bot_ip, idempotency_key=""):
        """Insert a completed order record into the orders table."""
        conn = self._conn()
        conn.execute(
            "INSERT INTO orders (order_id, chain, count, amount_usd, payment_tx, status, created_at, bot_ip, idempotency_key) "
            "VALUES (?, ?, ?, ?, ?, 'completed', ?, ?, ?)",
            (
                order_id,
                chain,
                count,
                amount,
                payment_tx or "free",
                time.time(),
                bot_ip,
                idempotency_key,
            ),
        )
        conn.commit()
        conn.close()


_db: _DB | None = None


def get_db() -> _DB:
    """Return the singleton marketplace database instance."""
    global _db
    if _db is None:
        _db = _DB(cfg.data_dir / "marketplace.db")
    return _db


async def _verify_onchain_payment(chain: str, tx: str, expected: float) -> bool:
    """Verify an on-chain USDC payment. Return True for free orders or verified payments."""
    if expected <= 0:
        return True
    if not tx:
        return False
    from core.x402_verify import verify_usdc_payment

    result = await verify_usdc_payment(chain, tx, expected)
    return result["verified"]


def _generate_wallets_sync(
    chain: str, count: int, order_id: str, derivation_path: str = "", xpub: str = ""
) -> list[dict]:
    """Generate wallets synchronously (runs in background thread for async jobs)."""
    # Access get_generator through the package so tests can monkeypatch it.
    import core.x402_marketplace as _pkg

    generator = _pkg.get_generator()
    wallets = []
    if xpub:
        from contextlib import suppress

        from bip_utils import Bip32Secp256k1, Bip32Slip10Ed25519

        chain_info = CHAINS.get(chain)
        if chain_info:
            with suppress(Exception):
                if chain_info.curve == "ed25519":
                    bip32_ctx = Bip32Slip10Ed25519.FromXPub(xpub)
                else:
                    bip32_ctx = Bip32Secp256k1.FromXPub(xpub)
                for i in range(count):
                    child_path = f"0/{i}"
                    child_key = bip32_ctx.DerivePath(child_path)
                    pub_bytes = child_key.PublicKey().Raw().ToBytes()
                    wallets.append(
                        {
                            "index": i + 1,
                            "address": pub_bytes.hex()[:40],
                            "private_key": "",
                            "mnemonic": "",
                            "derivation_path": child_path,
                            "derivation_method": "xpub",
                        }
                    )
    else:
        for i in range(count):
            gen_kwargs = {
                "chain_key": chain,
                "label": f"x402_{order_id}_{i}",
                "tags": ["x402", order_id],
            }
            if derivation_path:
                gen_kwargs["derivation_path"] = derivation_path
            wallet = generator.generate(**gen_kwargs)
            wallets.append(
                {
                    "index": i + 1,
                    "address": wallet.address,
                    "private_key": wallet.private_key_hex,
                    "mnemonic": wallet.mnemonic,
                    "derivation_path": wallet.derivation_path,
                }
            )
    return wallets


def _run_async_job(
    job_id: str,
    chain: str,
    count: int,
    order_id: str,
    derivation_path: str,
    xpub: str,
    webhook_url: str = "",
):
    """Background worker for async generation jobs."""
    try:
        wallets = _generate_wallets_sync(chain, count, order_id, derivation_path, xpub)
        with _jobs_lock:
            _jobs[job_id] = {"status": "completed", "wallets": wallets, "completed_at": time.time()}
        if webhook_url:
            # Fire-and-forget webhook delivery; failures must not fail the job.
            from contextlib import suppress

            import httpx

            with suppress(Exception):
                httpx.post(
                    webhook_url,
                    json={
                        "event": "job.completed",
                        "job_id": job_id,
                        "order_id": order_id,
                        "chain": chain,
                        "count": count,
                        "wallets": wallets,
                    },
                    timeout=15,
                )
    except Exception as e:
        with _jobs_lock:
            _jobs[job_id] = {"status": "failed", "error": str(e), "completed_at": time.time()}


def _refill_warm_pool():
    """Background task: keep warm pool filled for popular chains."""
    for chain in ("sol", "eth", "base", "polygon", "arbitrum"):
        with _WARM_POOL_LOCK:
            current = len(_WARM_POOL.get(chain, []))
        if current < _WARM_POOL_MIN:
            needed = min(_WARM_POOL_TARGET - current, _WARM_POOL_MAX_BATCH)
            if needed > 0:
                wallets = _generate_wallets_sync(chain, needed, f"warmpool_{chain}")
                with _WARM_POOL_LOCK:
                    _WARM_POOL.setdefault(chain, []).extend(wallets)
                    logger.info(
                        f"Warm pool refilled: {chain} +{needed} (total {len(_WARM_POOL[chain])})"
                    )


def _pull_from_warm_pool(chain: str, count: int) -> list[dict]:
    """Pull wallets from the warm pool. Returns empty list if pool is cold."""
    with _WARM_POOL_LOCK:
        pool = _WARM_POOL.get(chain, [])
        if len(pool) < count:
            return []
        taken = pool[:count]
        _WARM_POOL[chain] = pool[count:]
    return taken
