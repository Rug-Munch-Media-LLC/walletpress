"""Service metadata and health endpoints (public, no auth)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.config import cfg

router = APIRouter()


@router.get(
    "/health",
    summary="Health",
    description="Health check endpoint. Checks vault, key store, proof of generation, and webhook deliverer status.",
)
async def health():
    status = "ok"
    checks = {}

    try:
        from core.vault import get_vault

        get_vault().count()
        checks["vault"] = "ok"
    except Exception as e:
        checks["vault"] = f"error: {e}"
        status = "degraded"

    try:
        from core.auth import get_key_store

        get_key_store().list()
        checks["key_store"] = "ok"
    except Exception as e:
        checks["key_store"] = f"error: {e}"
        status = "degraded"

    try:
        from core.proof import get_proof

        get_proof().stats()
        checks["proof"] = "ok"
    except Exception as e:
        checks["proof"] = f"error: {e}"
        status = "degraded"

    try:
        from core.webhooks import get_webhook_deliverer

        deliverer = get_webhook_deliverer()
        checks["webhooks"] = "ok" if deliverer._running else "not_running"
    except Exception as e:
        checks["webhooks"] = f"error: {e}"
        status = "degraded"

    return JSONResponse(
        status_code=503 if status == "degraded" else 200,
        content={
            "status": status,
            "version": cfg.version,
            "service": "walletpress",
            "checks": checks,
        },
    )


@router.get("/version", summary="Version", description="Service version endpoint.")
async def version():
    """Return the running version and service metadata."""
    return {
        "version": cfg.version,
        "service": "WalletPress API",
        "title": cfg.title,
        "description": cfg.description,
        "status": "operational",
    }


@router.get(
    "/",
    summary="Root",
    description="API root endpoint. Returns service metadata, version, docs links, and trust/security information.",
)
async def root():
    """Return service metadata and the trust posture of this build."""
    from core.proof import get_source_tree_hash

    return {
        "service": "WalletPress API",
        "version": cfg.version,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "repository": "https://github.com/cryptorugmuncher/walletpress",
        "source_commit": get_source_tree_hash(),
        "trust": {
            "open_source": True,
            "telemetry": False,
            "client_side_generation": True,
            "encryption": "AES-256-GCM + Argon2id",
            "standards": ["BIP39", "BIP32", "BIP44", "BIP49", "BIP84"],
            "reproducible_builds": True,
            "build_verification": "/trust/build",
        },
    }
