"""WalletPress JWT Authentication Middleware.

Validates JWT tokens issued by rmi-backend (rugmunch.io) alongside
the existing WP_ADMIN_KEY (legacy) and API key authentication.

Dual-mode support:
    1. WP_ADMIN_KEY env var (legacy) — unchanged behavior
    2. Authorization: Bearer <jwt> — JWT from rmi-backend
    3. X-API-Key header — WalletPress API key (existing)

The JWT public key is fetched from rmi-backend's JWKS endpoint on
first use, or configured directly via WP_JWT_PUBLIC_KEY env var.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("wp.jwt_auth")

# ── Configuration ─────────────────────────────────────────────────────────────
_JWT_ALGORITHM: str = os.getenv("WP_JWT_ALGORITHM", "RS256")
_JWT_PUBLIC_KEY: str = os.getenv("WP_JWT_PUBLIC_KEY", "")
_JWKS_URL: str = os.getenv(
    "WP_JWKS_URL", "https://rugmunch.io/.well-known/jwks.json"
)
_JWKS_CACHE_TTL: int = int(os.getenv("WP_JWKS_CACHE_TTL", "3600"))  # 1 hour

# Cache for fetched JWKS key
_jwks_cache: dict[str, Any] = {"key": None, "fetched_at": 0.0}


def _fetch_jwks() -> str | None:
    """Fetch the RSA public key from rmi-backend's JWKS endpoint.

    Caches the result for WP_JWKS_CACHE_TTL seconds.
    Falls back to WP_JWT_PUBLIC_KEY env var if fetch fails.
    """
    now = time.time()
    if _jwks_cache["key"] and (now - _jwks_cache["fetched_at"]) < _JWKS_CACHE_TTL:
        return _jwks_cache["key"]

    # Try env var first (fast path, no network call)
    if _JWT_PUBLIC_KEY:
        key = _load_key(_JWT_PUBLIC_KEY)
        _jwks_cache["key"] = key
        _jwks_cache["fetched_at"] = now
        return key

    # Fetch from JWKS endpoint
    try:
        req = urllib.request.Request(_JWKS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        # Try JWKS format first
        keys = data.get("keys", [])
        if keys and len(keys) > 0:
            # Extract PEM from JWKS or use the 'pem' fallback
            if "pem" in data:
                _jwks_cache["key"] = data["pem"]
                _jwks_cache["fetched_at"] = now
                return data["pem"]
            # Try to extract x5c or n/e from JWK
            logger.warning("JWKS returned no PEM fallback — trying PEM env var instead")
        elif "pem" in data:
            _jwks_cache["key"] = data["pem"]
            _jwks_cache["fetched_at"] = now
            return data["pem"]
    except Exception as exc:
        logger.warning("Failed to fetch JWKS from %s: %s", _JWKS_URL, exc)

    return None


def _load_key(key_or_path: str) -> str:
    """Load a PEM key from a file path, or return the PEM string directly."""
    if os.path.exists(key_or_path) and os.path.isfile(key_or_path):
        with open(key_or_path) as _f:
            return _f.read()
    return key_or_path


def validate_rmi_jwt(token: str) -> dict[str, Any] | None:
    """Validate a JWT issued by rmi-backend.

    Args:
        token: The raw JWT string (without 'Bearer ' prefix).

    Returns:
        Dict with user claims (id, email, tier, role, wallet) or None if invalid.
    """
    if not token:
        return None

    key = _fetch_jwks()
    if not key:
        logger.error("No JWT public key available for validation")
        return None

    algorithm = "RS256" if _JWT_ALGORITHM == "RS256" else "HS256"
    try:
        payload = jwt.decode(token, key, algorithms=[algorithm])
    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        return None

    return {
        "id": payload.get("sub", ""),
        "email": payload.get("email", ""),
        "tier": payload.get("tier", "FREE"),
        "role": payload.get("role", "USER"),
        "wallet": payload.get("wallet"),
    }


class JWTValidationMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for JWT validation.

    Sits alongside the existing require_auth_on_mutations middleware.
    Accepts:
        1. ``Authorization: Bearer <jwt>`` — JWT from rmi-backend
        2. ``Authorization: Bearer <api_key>`` — WalletPress API key (existing)
        3. ``X-API-Key`` header — WalletPress API key (existing)

    For JWT-authenticated requests, attaches ``request.state.jwt_user``
    with the user claims. For API key requests, ``request.state.api_key_obj``
    continues to work unchanged.
    """

    def __init__(self, app: Any):
        super().__init__(app)
        self._public_key: str | None = _fetch_jwks()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip auth for public paths
        if path in ("/health", "/docs", "/openapi.json", "/metrics"):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        x_api_key = request.headers.get("X-API-Key", "")

        # If no auth present, let the existing middleware handle it
        if not auth and not x_api_key:
            request.state.jwt_user = None
            return await call_next(request)

        # Try JWT validation (Authorization: Bearer <token>)
        if auth.startswith("Bearer "):
            token = auth[7:]

            # Check if it's a WalletPress API key (starts with 'wp_')
            if token.startswith("wp_") or token == os.getenv("WP_ADMIN_KEY", ""):
                # Let existing auth middleware handle API keys
                request.state.jwt_user = None
                return await call_next(request)

            # Validate as JWT from rmi-backend
            claims = validate_rmi_jwt(token)
            if claims:
                request.state.jwt_user = claims
                return await call_next(request)

        # If we reach here, auth failed
        # Let existing middleware handle it for API keys,
        # but return 401 for malformed JWTs
        if auth.startswith("Bearer ") and not auth[7:].startswith("wp_"):
            from datetime import UTC, datetime
            return JSONResponse(
                status_code=401,
                content={
                    "type": "/errors/unauthorized",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "Invalid or expired JWT token",
                    "request_id": getattr(request.state, "request_id", ""),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "code": "unauthorized",
                },
            )

        return await call_next(request)
