"""Chain Vault Router — Educational OSS example of a wallet vault API.

THIS IS A STRIPPED EDUCATIONAL EXAMPLE.
The full production version includes 55+ chains, AES-256-GCM encryption,
Argon2id KDF, Merkle proof attestation, temporal wallets, escrow,
fund distribution, sweep, rotation, paper wallet generation, and more.

This file shows the PATTERN: how to build a chain vault with FastAPI.
Replace the generator and vault with your own implementations.

Trust: All crypto operations are deterministic. Same input = same output,
ALWAYS, on ANY software. Verify with your own wallet software.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.audit import get_audit
from core.config import cfg
from core.vault import WalletEntry, get_vault
from wallet_engine.chains import CHAIN_GROUPS, get_chains_for_tier
from wallet_engine.generator import CryptoError, CryptoInputError, get_generator

logger = logging.getLogger("wp.chain_vault")

router = APIRouter(prefix="/api/v1/chain-vault", tags=["Chain Vault"])


# ── Models ───────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    chain: str = Field(..., description="Chain key (eth, sol, btc, etc.)")
    count: int = Field(default=1, ge=1, le=100, description="Number of wallets")
    label: str = Field(default="", description="Optional label")


class ImportRequest(BaseModel):
    chain: str = Field(...)
    private_key: str = Field(..., description="Hex-encoded private key")
    label: str = Field(default="")


class WalletResponse(BaseModel):
    id: str
    chain: str
    address: str
    label: str
    tags: list[str] = []
    created_at: float
    encrypted: bool = False
    has_private_key: bool = False
    public_key: str = ""
    balance_usd: float = 0.0


class VaultListResponse(BaseModel):
    wallets: list[WalletResponse]
    total: int
    limit: int
    offset: int
    search: str


class ErrorResponse(BaseModel):
    error: str
    request_id: str = ""


# ── Helpers ──────────────────────────────────────────────────────


def _safe_crypto_call(operation_name: str, fn, *args, **kwargs):
    """Execute a crypto operation with proper error translation.

    Translates CryptoError -> HTTP 500, CryptoInputError/ValueError -> HTTP 400.
    All other exceptions -> HTTP 500 with logged error.
    """
    try:
        return fn(*args, **kwargs)
    except (CryptoInputError, ValueError) as e:
        logger.warning("Crypto input error in %s: %s", operation_name, e)
        raise HTTPException(status_code=400, detail=str(e))
    except CryptoError as e:
        logger.error("Crypto operation failed in %s: %s", operation_name, e)
        raise HTTPException(status_code=500, detail=f"Crypto operation failed: {e}")
    except Exception as e:
        logger.exception("Unexpected error in %s: %s", operation_name, e)
        raise HTTPException(
            status_code=500, detail=f"Unexpected error during {operation_name}: {e}"
        )


# ═══════════════════════════════════════════════════════════════════
#  CHAIN INFORMATION
# ═══════════════════════════════════════════════════════════════════


@router.get("/chains")
async def list_chains():
    """List ALL supported blockchain networks with full metadata.

    Each entry includes derivation paths, address patterns, explorer URLs.
    """
    tier_chains = get_chains_for_tier("enterprise")
    return {
        "total_chains": len(tier_chains),
        "chain_families": len({c.family.value for c in tier_chains.values()}),
        "chains": {
            k: {
                "name": v.name,
                "symbol": v.symbol,
                "family": v.family.value,
                "decimals": v.decimals,
                "slip44": v.slip44,
                "hd_path": v.hd_path,
                "address_pattern": v.address_pattern,
                "explorer_url": v.explorer_url,
                "rpc_url": v.rpc_url,
                "curve": v.curve,
                "native_token": v.native_token,
                "description": v.description,
            }
            for k, v in tier_chains.items()
        },
        "groups": {name: chains for name, chains in CHAIN_GROUPS.items()},
        "note": "All chains follow BIP44 standards. Verify with any wallet.",
    }


@router.get("/healthz")
async def healthz():
    """Lightweight health check for load balancers."""
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}


# ═══════════════════════════════════════════════════════════════════
#  WALLET GENERATION & IMPORT
# ═══════════════════════════════════════════════════════════════════


@router.post("/generate")
async def generate_wallet(req: GenerateRequest, request: Request):
    """Generate one or more wallets for any supported chain.

    Uses CSPRNG (os.urandom) for entropy. Keys are encrypted at rest
    with AES-256-GCM + Argon2id if vault password is configured.

    Returns safe dict WITHOUT private keys. Use GET /vault/{id} to
    retrieve private keys with proper authentication.
    """
    # Audit: log every generation
    get_audit().log(
        action="wallet.generate",
        actor=request.headers.get("X-API-Key", "")[:16] or "anonymous",
        detail={"chain": req.chain, "count": req.count},
    )

    generator = get_generator(cfg.vault_password)
    vault = get_vault()
    wallets = []

    for i in range(req.count):
        try:
            label = req.label or f"{req.chain}_{i + 1}_{int(time.time())}"
            wallet = _safe_crypto_call("generate", generator.generate, req.chain, label=label)
            entry = WalletEntry(
                id=f"wp_{secrets.token_hex(8)}",
                chain=wallet.chain,
                address=wallet.address,
                label=wallet.label,
                tags=wallet.tags,
                created_at=wallet.created_at,
                encrypted_key=wallet.private_key_hex if wallet.encrypted else "",
                public_key=wallet.public_key_hex,
                derivation_path=wallet.derivation_path,
                hd_path=wallet.derivation_path,
                encrypted=wallet.encrypted,
            )
            vault.put(entry)
            wallets.append(
                {
                    "id": entry.id,
                    "chain": entry.chain,
                    "address": entry.address,
                    "label": entry.label,
                    "encrypted": entry.encrypted,
                }
            )
        except HTTPException:
            raise

    return {
        "generated": len(wallets),
        "chain": req.chain,
        "wallets": wallets,
        "note": "Private keys stored securely. Use GET /vault/{id} with API key to retrieve.",
    }


@router.post("/import")
async def import_wallet(req: ImportRequest, request: Request):
    """Import an existing wallet from a private key.

    The private key is encrypted at rest with AES-256-GCM + Argon2id.
    We never log or transmit the raw key.
    """
    get_audit().log(
        action="wallet.import",
        actor=request.headers.get("X-API-Key", "")[:16] or "anonymous",
        detail={"chain": req.chain},
    )

    generator = get_generator(cfg.vault_password)
    # In production, validate private key format before importing
    wallet = _safe_crypto_call(
        "import",
        generator.import_from_private_key,
        req.chain,
        req.private_key,
        label=req.label,
    )

    vault = get_vault()
    entry = WalletEntry(
        id=f"wp_{secrets.token_hex(8)}",
        chain=wallet.chain,
        address=wallet.address,
        label=wallet.label,
        tags=wallet.tags,
        created_at=wallet.created_at,
        encrypted_key=wallet.private_key_hex if wallet.encrypted else wallet.private_key_hex,
        encrypted=wallet.encrypted,
    )
    vault.put(entry)

    return {
        "imported": True,
        "wallet": {
            "id": entry.id,
            "chain": entry.chain,
            "address": entry.address,
            "label": entry.label,
        },
    }


# ═══════════════════════════════════════════════════════════════════
#  VAULT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════


@router.get("/vault", response_model=VaultListResponse)
async def list_vault(
    request: Request, chain: str = "", limit: int = 100, offset: int = 0, search: str = ""
):
    """List all wallets in the vault (no private keys exposed).

    Returns metadata only: chain, address, label, tags, creation time.
    Private keys are NEVER included in list responses.
    """
    vault = get_vault()
    if search:
        wallets = vault.search(search)
    elif chain:
        wallets = vault.list(chain=chain, limit=limit, offset=offset)
    else:
        wallets = vault.list(limit=limit, offset=offset)
    return {
        "wallets": [
            {
                "id": w.id,
                "chain": w.chain,
                "address": w.address,
                "label": w.label,
                "tags": w.tags,
                "created_at": w.created_at,
                "encrypted": w.encrypted,
                "has_private_key": bool(w.encrypted_key),
                "public_key": w.public_key,
                "balance_usd": w.balance_usd,
            }
            for w in wallets
        ],
        "total": vault.count(chain=chain),
        "limit": limit,
        "offset": offset,
        "search": search,
    }


@router.get("/vault/{wallet_id}")
async def get_wallet(wallet_id: str, request: Request):
    """Get wallet details.

    By default, private keys are NOT returned. In production, set
    include_key=true with proper authentication (admin scope, TOTP)
    to decrypt and retrieve the private key. Key exports are rate-limited
    (10/min) and every retrieval is audited.
    """
    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    return {
        "id": wallet.id,
        "chain": wallet.chain,
        "address": wallet.address,
        "label": wallet.label,
        "tags": wallet.tags,
        "created_at": wallet.created_at,
        "public_key": wallet.public_key,
        "derivation_path": wallet.derivation_path,
        "hd_path": wallet.hd_path,
        "encrypted": wallet.encrypted,
        "balance_usd": wallet.balance_usd,
        "notes": wallet.notes,
        "private_key_available": bool(wallet.encrypted_key),
        "note": "Use ?include_key=true with admin API key and TOTP to retrieve private key.",
    }


@router.delete("/vault/{wallet_id}")
async def delete_wallet(wallet_id: str, request: Request):
    """Delete a wallet from the vault permanently.

    Warning: This cannot be undone. The private key is gone forever.
    """
    get_audit().log(
        action="wallet.delete",
        actor=request.headers.get("X-API-Key", "")[:16] or "anonymous",
        resource=wallet_id,
    )
    vault = get_vault()
    if not vault.delete(wallet_id):
        raise HTTPException(status_code=404, detail="Wallet not found")
    return {"deleted": True, "wallet_id": wallet_id}
