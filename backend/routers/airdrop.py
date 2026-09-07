"""Bulk wallet airdrop tool — generate 10k+ wallets, create distribution manifests.

This is the $99-499 add-on. For token launches, NFT mints, and community
distributions that need wallet generation at scale.

WORKFLOW:
  1. Upload CSV with recipient data (email, amount, notes)
  2. Generate wallets for all recipients
  3. Export distribution manifest (CSV/JSON)
  4. Generate signed transactions for on-chain distribution
  5. Download detailed report

Trust: Each recipient gets a unique wallet. No two wallets share keys.
The distribution manifest is proof of the airdrop plan before execution.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import secrets
import sqlite3
import time
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path

from core.audit import get_audit as _get_audit_log
from core.vault import WalletEntry, get_vault


def _audit(action, request, resource="", detail=None):
    _get_audit_log().log(
        action=action,
        actor=request.headers.get("X-API-Key", "")[:16] or "anonymous",
        resource=resource,
        detail=detail or {},
        ip=request.client.host if request.client else "",
    )


from wallet_engine.chains import CHAINS
from wallet_engine.generator import get_generator

logger = logging.getLogger("wp.airdrop")

router = APIRouter(prefix="/api/v1/airdrop", tags=["Airdrop"])


class AirdropRequest(BaseModel):
    chain: str = Field(default="sol", description="Chain for all wallets")
    label_prefix: str = Field(default="airdrop", description="Label prefix for all wallets")
    total_wallets: int = Field(
        default=100, ge=1, le=100000, description="Number of wallets to generate"
    )
    recipients: list[dict] = Field(default_factory=list, description="Optional recipient list")


class DistributeRequest(BaseModel):
    manifest_id: str = Field(...)
    chain: str = Field(...)
    token_mint: str = Field(default="", description="Token mint address for SPL/ERC20")
    amounts: dict[str, float] = Field(
        default_factory=dict, description="wallet_address -> amount mapping"
    )


_manifests: dict[str, dict] = {}
_MANIFEST_DB_PATH: Path | None = None

# Fire-and-forget background tasks (e.g. webhook emissions) kept alive so the
# event loop doesn't garbage-collect them mid-flight.
_background_tasks: set[asyncio.Task] = set()


def _get_manifest_db() -> Path:
    global _MANIFEST_DB_PATH
    if _MANIFEST_DB_PATH is None:
        from core.config import cfg

        _MANIFEST_DB_PATH = cfg.data_dir / "airdrop_manifests.db"
    return _MANIFEST_DB_PATH


def _init_manifest_db():
    db_path = _get_manifest_db()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS manifests (
            manifest_id TEXT PRIMARY KEY,
            chain TEXT NOT NULL,
            total_wallets INTEGER NOT NULL,
            data TEXT NOT NULL,
            created_at REAL NOT NULL,
            status TEXT DEFAULT 'generated'
        )
    """)
    conn.commit()
    conn.close()


def _save_manifest(manifest: dict):
    _init_manifest_db()
    conn = sqlite3.connect(str(_get_manifest_db()))
    conn.execute(
        "INSERT OR REPLACE INTO manifests (manifest_id, chain, total_wallets, data, created_at, status) VALUES (?, ?, ?, ?, ?, ?)",
        (
            manifest["manifest_id"],
            manifest["chain"],
            manifest["total_wallets"],
            json.dumps(manifest),
            manifest["created_at"],
            manifest["status"],
        ),
    )
    conn.commit()
    conn.close()


def _load_manifest(manifest_id: str) -> dict | None:
    _init_manifest_db()
    conn = sqlite3.connect(str(_get_manifest_db()))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT data FROM manifests WHERE manifest_id = ?", (manifest_id,)
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row["data"])
    return None


def _load_all_manifests() -> list[dict]:
    _init_manifest_db()
    conn = sqlite3.connect(str(_get_manifest_db()))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT data FROM manifests ORDER BY created_at DESC").fetchall()
    conn.close()
    return [json.loads(r["data"]) for r in rows]


@router.post("/generate")
async def airdrop_generate(req: AirdropRequest, request: Request):
    """Generate wallets in bulk for airdrop distribution.

    Creates N wallets on the specified chain, stores them in the vault,
    and returns a distribution manifest with all addresses.

    For 10,000 wallets, this takes approximately 30-60 seconds.
    """
    from core.config import cfg
    from core.webhooks import get_webhook_deliverer

    # Fail closed: refuse bulk generation when the vault password is unset —
    # generated private keys would be silently discarded (stored unencrypted
    # is not an option for airdrop wallets holding real funds).
    if not cfg.vault_password:
        raise HTTPException(
            status_code=503,
            detail=(
                "Vault password not configured (WP_VAULT_PASSWORD). "
                "Refusing to generate airdrop wallets without at-rest key encryption. "
                "Set WP_VAULT_PASSWORD and restart the service."
            ),
        )

    generator = get_generator(cfg.vault_password)
    vault = get_vault()

    _audit("airdrop.generate", request, detail={"chain": req.chain, "count": req.total_wallets})

    manifest_id = f"airdrop_{secrets.token_hex(8)}"
    wallets = []
    chain_info = CHAINS.get(req.chain.lower())

    for i in range(req.total_wallets):
        label = f"{req.label_prefix}_{i + 1}"
        wallet = generator.generate(req.chain, label=label, tags=["airdrop", manifest_id])

        entry = WalletEntry(
            id=f"air_{secrets.token_hex(4)}_{i}",
            chain=wallet.chain,
            address=wallet.address,
            label=wallet.label,
            tags=["airdrop", manifest_id],
            created_at=wallet.created_at,
            encrypted_key=wallet.private_key_hex if generator._vault_password else "",
            encrypted=bool(generator._vault_password),
        )
        vault.put(entry)

        recipient = req.recipients[i] if i < len(req.recipients) else {}
        wallets.append(
            {
                "index": i + 1,
                "wallet_id": entry.id,
                "address": wallet.address,
                "label": wallet.label,
                "recipient_email": recipient.get("email", ""),
                "amount": recipient.get("amount", 0),
            }
        )

    manifest = {
        "manifest_id": manifest_id,
        "chain": req.chain,
        "chain_name": chain_info.name if chain_info else req.chain,
        "total_wallets": len(wallets),
        "created_at": time.time(),
        "status": "generated",
        "wallets": wallets,
    }
    _manifests[manifest_id] = manifest
    _save_manifest(manifest)

    task = asyncio.ensure_future(
        get_webhook_deliverer().emit(
            "airdrop.generated",
            {
                "manifest_id": manifest_id,
                "chain": req.chain,
                "count": len(wallets),
            },
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "manifest_id": manifest_id,
        "total_wallets": len(wallets),
        "chain": req.chain,
        "wallets": [
            {"index": w["index"], "address": w["address"], "recipient_email": w["recipient_email"]}
            for w in wallets
        ],
        "note": f"Generated {len(wallets)} wallets. Use GET /airdrop/manifest/{manifest_id} to export.",
    }


@router.get("/manifest/{manifest_id}")
async def airdrop_manifest(manifest_id: str, fmt: Annotated[str, Query(alias="format")] = "json"):
    """Export a distribution manifest in CSV or JSON format.

    CSV format: index,address,private_key,label,recipient_email,amount
    JSON format: full manifest with all metadata

    Private keys are ONLY included if vault encryption is disabled.
    """
    manifest = _manifests.get(manifest_id) or _load_manifest(manifest_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Manifest not found")
    _manifests[manifest_id] = manifest  # warm cache

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["index", "address", "label", "recipient_email", "amount"])
        for w in manifest["wallets"]:
            writer.writerow(
                [w["index"], w["address"], w["label"], w["recipient_email"], w["amount"]]
            )
        return {
            "format": "csv",
            "filename": f"airdrop_{manifest_id}.csv",
            "data": output.getvalue(),
        }

    return {
        "manifest": manifest,
        "total_wallets": manifest["total_wallets"],
        "export_date": time.time(),
    }


@router.get("/manifest/{manifest_id}/report")
async def airdrop_report(manifest_id: str):
    """Generate a distribution report with wallet stats."""
    manifest = _manifests.get(manifest_id) or _load_manifest(manifest_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Manifest not found")
    _manifests[manifest_id] = manifest

    wallets = manifest["wallets"]
    return {
        "manifest_id": manifest_id,
        "report": {
            "total_wallets": len(wallets),
            "with_recipient": sum(1 for w in wallets if w.get("recipient_email")),
            "with_amount": sum(1 for w in wallets if w.get("amount", 0) > 0),
            "total_distribution_usd": sum(w.get("amount", 0) for w in wallets),
        },
        "manifests": _manifests[manifest_id],
    }


@router.get("/manifests")
async def airdrop_manifests():
    """List all distribution manifests."""
    all_m = list(_manifests.values()) if _manifests else _load_all_manifests()
    if not all_m:
        all_m = list(_manifests.values())
    return {
        "manifests": [
            {
                "manifest_id": m["manifest_id"],
                "chain": m["chain"],
                "total_wallets": m["total_wallets"],
                "created_at": m["created_at"],
                "status": m["status"],
            }
            for m in all_m
        ],
        "total": len(all_m),
    }
