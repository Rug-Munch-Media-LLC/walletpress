"""License enforcement — middleware for global checks, Depends() for per-route.

Two-layer approach:
  1. LicenseMiddleware — global, path-based, catches obvious blocks early.
  2. require_feature() — FastAPI dependency, injectable per-route for granular
     control. Decouples licensing from URL structure.
"""

from __future__ import annotations


from fastapi import HTTPException, Request, status
from fastapi.params import Depends
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from .license import FEATURES, get_license


# ── Per-route dependency (preferred) ─────────────────────────────

def require_feature(feature: str):
    """FastAPI dependency that checks a license feature.

    Use on individual routes instead of coupling licensing to URL paths:
        @router.post("/batch", dependencies=[Depends(require_feature("batch_generation"))])

    Raises 402 with upsell info if the feature is not available.
    """
    TIER_UPSELL = {
        "community": {"next": "starter", "price": 49, "url": "https://walletpress.cc/buy.html"},
        "starter": {"next": "pro", "price": 199, "url": "https://walletpress.cc/buy.html"},
        "pro": {"next": "enterprise", "price": 499, "url": "https://walletpress.cc/buy.html"},
    }

    async def dependency(request: Request) -> None:
        lic = get_license()
        if lic.has_feature(feature):
            return
        tier = lic.tier
        upsell = TIER_UPSELL.get(tier, TIER_UPSELL["community"])
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail={
            "error": f"Feature '{feature}' requires {upsell['next'].title()} tier or higher",
            "current_tier": tier,
            "required_tier": upsell["next"],
            "price_usd": upsell["price"],
            "upgrade_url": upsell["url"],
        })

    return Depends(dependency)


# ── Global middleware (fallback) ─────────────────────────────────

class LicenseMiddleware(BaseHTTPMiddleware):
    """Path-based middleware for coarse-grained license enforcement.

    Prefer require_feature() on individual routes for new endpoints.
    This middleware is kept for backward compatibility and as a defense-in-depth
    layer for any routes that forgot the dependency.
    """

    EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/metrics",
                       "/api/v1/test-vectors", "/api/v1/marketplace/pricing",
                       "/api/v1/license", "/hosting/plans")

    TIER_UPSELL = {
        "community": {"next": "starter", "price": 49, "url": "https://walletpress.cc/buy.html"},
        "starter": {"next": "pro", "price": 199, "url": "https://walletpress.cc/buy.html"},
        "pro": {"next": "enterprise", "price": 499, "url": "https://walletpress.cc/buy.html"},
    }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return await call_next(request)

        lic = get_license()
        tier = lic.tier

        if tier == "community" and path.startswith("/api/v1/chain-vault/generate"):
            if request.method == "POST":
                body = await request.json()
                chain = body.get("chain", "")
                allowed = lic.get_chain_list()
                if chain and chain not in allowed:
                    upsell = self.TIER_UPSELL["community"]
                    return JSONResponse(status_code=402, content={
                        "detail": {
                            "error": f"Chain '{chain}' requires {upsell['next'].title()} tier or higher",
                            "current_tier": tier,
                            "required_tier": upsell["next"],
                            "price_usd": upsell["price"],
                            "available_chains": allowed,
                            "upgrade_url": upsell["url"],
                        }
                    })

        if tier == "community" and path.startswith(("/api/v1/chain-vault/generate/batch", "/api/v1/airdrop/")):
            if request.method == "POST":
                body = await request.json()
                count = body.get("count", 0) or len(body.get("chains", []))
                if count > 1 and not lic.check_batch_limit(count):
                    upsell = self.TIER_UPSELL["community"]
                    return JSONResponse(status_code=402, content={
                        "detail": {
                            "error": f"Batch of {count} requires {upsell['next'].title()} tier or higher",
                            "current_tier": tier,
                            "required_tier": upsell["next"],
                            "max_batch": FEATURES["community"]["batch_max"],
                            "price_usd": upsell["price"],
                            "upgrade_url": upsell["url"],
                        }
                    })

        return await call_next(request)
