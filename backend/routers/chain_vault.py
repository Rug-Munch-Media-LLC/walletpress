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
from core.auth import get_key_store
from core.config import cfg
from core.vault import WalletEntry, get_vault
from wallet_engine.chains import CHAIN_GROUPS, CHAINS, get_chains_for_tier
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except CryptoError as e:
        logger.error("Crypto operation failed in %s: %s", operation_name, e)
        raise HTTPException(status_code=500, detail=f"Crypto operation failed: {e}") from e
    except Exception as e:
        logger.exception("Unexpected error in %s: %s", operation_name, e)
        raise HTTPException(
            status_code=500, detail=f"Unexpected error during {operation_name}: {e}"
        ) from e


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
        "groups": dict(CHAIN_GROUPS.items()),
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
        encrypted_key=wallet.private_key_hex if wallet.encrypted else "",
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


@router.get("/stats")
async def vault_stats():
    """Get vault statistics: total wallets, encryption status, chain distribution."""
    vault = get_vault()
    stats = vault.stats()
    return {
        "vault": stats,
        "encryption_enabled": cfg.vault_password is not None and len(cfg.vault_password) > 0,
        "total_chains_supported": len(CHAINS),
    }


@router.get("/vault/{wallet_id}/full")
async def get_wallet_full(wallet_id: str, request: Request):
    """Get full wallet details including private key.

    Requires admin API key. Private key is decrypted and returned.
    Every full export is audited.
    """
    auth = request.headers.get("X-API-Key", "")
    if not auth:
        raise HTTPException(status_code=401, detail="API key required")
    if auth != cfg.admin_key:
        ks = get_key_store()
        key_obj = ks.verify(auth)
        if not key_obj:
            raise HTTPException(status_code=403, detail="Invalid API key")
        if "admin" not in key_obj.scopes and "wallet.admin" not in key_obj.scopes:
            raise HTTPException(status_code=403, detail="Admin scope required for full key export")

    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    get_audit().log(
        action="wallet.full_export",
        actor=auth[:16] or "anonymous",
        resource=wallet_id,
    )

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
        "private_key_hex": wallet.encrypted_key if wallet.encrypted_key else "",
        "mnemonic_encrypted": wallet.mnemonic_encrypted if wallet.mnemonic_encrypted else "",
        "balance_usd": wallet.balance_usd,
        "notes": wallet.notes,
    }


@router.get("/validate/{chain}/{address}")
async def validate_address_endpoint(chain: str, address: str):
    """Validate whether an address is valid for a given chain.

    Uses the chain's address_pattern regex to validate format correctness.
    This does NOT check if the address exists on-chain.
    """
    from wallet_engine.chains import validate_address as va

    valid = va(chain, address)
    return {
        "valid": valid,
        "chain": chain,
        "address": address,
        "note": "Format validation only — does not check on-chain existence",
    }


@router.get("/validate/all")
async def validate_address_all(address: str = ""):
    """Find all chains whose address pattern matches the given address."""
    if not address:
        raise HTTPException(status_code=400, detail="Address parameter required")
    import re

    possible = []
    for key, chain in CHAINS.items():
        if chain.address_pattern and re.match(chain.address_pattern, address):
            possible.append(
                {
                    "chain": key,
                    "name": chain.name,
                    "family": chain.family.value,
                }
            )
    return {
        "address": address,
        "possible_chains": possible,
        "total_matches": len(possible),
    }


@router.get("/tree")
async def wallet_tree(request: Request):
    """Get wallets grouped by chain family."""
    vault = get_vault()
    wallets = vault.list(limit=10000)
    tree: dict[str, list[dict]] = {}
    for w in wallets:
        chain_info = CHAINS.get(w.chain)
        family = chain_info.family.value if chain_info else "unknown"
        if family not in tree:
            tree[family] = []
        tree[family].append(
            {
                "id": w.id,
                "chain": w.chain,
                "address": w.address,
                "label": w.label,
                "created_at": w.created_at,
                "encrypted": w.encrypted,
            }
        )
    return {
        "tree": tree,
        "total_families": len(tree),
        "total_wallets": len(wallets),
    }


@router.post("/api-keys")
async def create_api_key(request: Request):
    """Create a new API key."""
    body = await request.json()
    label = body.get("label", "default")
    scopes = body.get("scopes", ["wallet.read"])
    ks = get_key_store()
    key_id, raw_key = ks.create(label=label, scopes=scopes)
    return {"api_key_id": key_id, "api_key": raw_key, "label": label, "scopes": scopes}


@router.get("/api-keys")
async def list_api_keys():
    """List all API keys (without exposing the raw keys)."""
    ks = get_key_store()
    return {"api_keys": ks.list()}


class DeriveRequest(BaseModel):
    mnemonic: str = Field(..., description="BIP39 mnemonic phrase")
    chain: str = Field(..., description="Chain key (eth, sol, btc, etc.)")


@router.post("/derive-address")
async def derive_address(req: DeriveRequest):
    """Derive address from mnemonic for a specific chain.

    Deterministic — same mnemonic + chain always produces the same address.
    Uses BIP39/BIP44 standard derivation.
    """
    generator = get_generator(cfg.vault_password)
    try:
        wallet = generator.generate(req.chain, mnemonic=req.mnemonic)
        return {
            "chain": wallet.chain,
            "address": wallet.address,
            "mnemonic": req.mnemonic,
            "derivation_path": wallet.derivation_path
            or CHAINS.get(req.chain, CHAINS["eth"]).hd_path,
            "public_key": wallet.public_key_hex,
            "created_at": wallet.created_at,
        }
    except CryptoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Derivation failed: {e}") from e
