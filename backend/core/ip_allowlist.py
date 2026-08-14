"""IP allowlisting middleware for admin operations.

When WP_ALLOWED_IPS is set, all requests from non-whitelisted IPs
are rejected. This prevents leaked API keys from being used off-network.

Trust: IP allowlisting means even if your API key is compromised,
an attacker can't use it from a different IP address.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

if TYPE_CHECKING:
    from starlette.responses import Response

ALLOWED_IPS: list[str] = []
_raw = os.getenv("WP_ALLOWED_IPS", "")
if _raw:
    ALLOWED_IPS = [ip.strip() for ip in _raw.split(",")]


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    """Rejects requests from non-whitelisted IPs when configured.

    Only applies to admin/sensitive endpoints.
    Health and public endpoints are exempt.
    """

    SENSITIVE_PREFIXES = (
        "/api/v1/chain-vault/admin",
        "/api/v1/chain-vault/vault/",
        "/api/v1/chain-vault/export",
        "/api/v1/chain-vault/proof/commit",
        "/api/v1/chain-vault/proof/verify",
        "/api/v1/chain-vault/paper-wallet",
        "/api/v1/chain-vault/tx/broadcast",
    )

    def __init__(self, app):
        super().__init__(app)
        self._enabled = len(ALLOWED_IPS) > 0

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._enabled:
            return await call_next(request)

        # Check if this is a sensitive endpoint
        is_sensitive = any(request.url.path.startswith(p) for p in self.SENSITIVE_PREFIXES)
        if not is_sensitive:
            return await call_next(request)

        client_ip = request.client.host if request.client else ""
        if client_ip not in ALLOWED_IPS and "0.0.0.0" not in ALLOWED_IPS:  # noqa: S104 — allowlist sentinel ("allow any IP"), not a bind address
            raise HTTPException(
                status_code=403,
                detail=f"Access denied from {client_ip}. Configure WP_ALLOWED_IPS to whitelist this IP.",
            )

        return await call_next(request)
