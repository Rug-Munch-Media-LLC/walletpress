"""License management endpoints — check status, generate keys (admin)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, HTTPException

from core.license import FEATURES, get_license

router = APIRouter(prefix="/api/v1/license", tags=["License"])

# Admin key for license generation (same as WP_ADMIN_KEY)
LICENSE_SECRET = os.getenv("WP_LICENSE_SECRET", "")


@router.get("")
async def license_status():
    """Get current license tier and available features."""
    lic = get_license()
    return lic.to_dict()


@router.get("/plans")
async def license_plans():
    """List all license tiers with features and pricing."""
    return {
        "plans": [
            {
                "id": k,
                "name": v["name"],
                "price_usd": v["price_usd"],
                "chains": v["chains"],
                "max_vault_wallets": v["max_vault_wallets"],
                "features": v["features"],
                "type": "one-time" if v["price_usd"] > 0 else "free",
            }
            for k, v in FEATURES.items()
        ],
        "current_tier": get_license().tier,
    }


@router.post("/generate")
async def generate_key(tier: str, expiry_days: int = 365, admin_key: str = ""):
    """Generate a license key (admin only)."""
    if tier not in FEATURES:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}")

    # Require either LICENSE_SECRET or WP_ADMIN_KEY, matching exact value
    if LICENSE_SECRET:
        if admin_key != LICENSE_SECRET:
            raise HTTPException(status_code=403, detail="Invalid admin key")
    elif os.getenv("WP_ADMIN_KEY"):
        if admin_key != os.getenv("WP_ADMIN_KEY", ""):
            raise HTTPException(status_code=403, detail="Invalid admin key")
    else:
        raise HTTPException(status_code=403, detail="License generation not configured — set WP_LICENSE_SECRET or WP_ADMIN_KEY")

    signing_key = LICENSE_SECRET or os.getenv("WP_ADMIN_KEY", "")
    if not signing_key:
        raise HTTPException(status_code=500, detail="No signing key configured")

    exp = int(time.time() + (expiry_days * 86400)) if expiry_days > 0 else 0
    payload = json.dumps({"tier": tier, "exp": exp}, sort_keys=True)
    sig = hmac.new(signing_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = base64.b64encode(json.dumps({"tier": tier, "exp": exp, "sig": sig}).encode()).decode()

    return {
        "license_key": token,
        "tier": tier,
        "expires": time.strftime("%Y-%m-%d", time.gmtime(exp)) if exp > 0 else "never",
        "instructions": f"Set WP_LICENSE_KEY={token} or save to /etc/walletpress/license.key",
    }
