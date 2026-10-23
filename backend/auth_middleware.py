"""Authentication and authorisation middleware.

* `require_auth_on_mutations` authenticates every request and enforces the
  minimum role (`operator`) on write methods.
* `require_admin_key_on_mcp` requires WP_ADMIN_KEY on every /mcp route and
  binds the authenticated actor for HITL confirmations.

Security history encoded here (not TODOs):
  - P0-3: a `viewer` key could mutate state; writes are role-checked now.
  - 2026-09-06: GET on vault/retention was unauthenticated and could return
    wallet metadata; every non-public path is authenticated now.
  - /mcp/ was exempt, so any caller could drain wallets through the agent
    surface; it is admin-key only, compared in constant time.
"""

from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request
from fastapi.responses import JSONResponse

from core.auth import APIKey, get_key_store, role_has_at_least
from core.config import cfg
from request_context import get_request_id

logger = logging.getLogger("wp")

WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
PUBLIC_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/metrics",
    "/hosting/register",
    "/hosting/login",
    "/mcp/",
    "/ws/",
)
_ERROR_TYPES = {401: "unauthorized", 403: "forbidden"}
_ERROR_TITLES = {401: "Unauthorized", 403: "Forbidden"}


def _error_response(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    """Build the standard error envelope used by the auth middlewares."""
    return JSONResponse(
        status_code=status,
        content={
            "type": f"/errors/{_ERROR_TYPES.get(status, 'error')}",
            "title": _ERROR_TITLES.get(status, "Error"),
            "status": status,
            "detail": detail,
            "request_id": get_request_id(request),
            "timestamp": datetime.now(UTC).isoformat(),
            "code": code,
        },
    )


def _resolve_api_key(credential: str) -> APIKey | None:
    """Return the APIKey for a credential, or None when invalid/revoked."""
    if credential == cfg.admin_key:
        return APIKey(
            id="env_admin",
            key_hash="env",
            label="env_admin",
            scopes=["admin"],
            created_at=0,
            role="admin",
        )
    return get_key_store().verify(credential)


async def require_auth_on_mutations(request: Request, call_next):
    """Authenticate all requests; require `operator` role on writes."""
    if not request.url.path.startswith(PUBLIC_PREFIXES):
        credential = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not credential:
            credential = request.headers.get("X-API-Key", "")
        if not credential:
            return _error_response(
                request,
                401,
                "unauthorized",
                "API key required. Provide via X-API-Key or Authorization: Bearer header.",
            )

        api_key_obj = _resolve_api_key(credential)
        if api_key_obj is None:
            return _error_response(request, 403, "forbidden", "Invalid or revoked API key")

        if request.method in WRITE_METHODS and not role_has_at_least(api_key_obj.role, "operator"):
            return _error_response(
                request,
                403,
                "forbidden",
                f"Insufficient role: '{api_key_obj.role}' cannot perform write operations. "
                "Required: operator or admin.",
            )

        request.state.api_key_obj = api_key_obj
    return await call_next(request)


async def require_admin_key_on_mcp(request: Request, call_next):
    """Require WP_ADMIN_KEY on every /mcp route (constant-time compare)."""
    if not request.url.path.startswith("/mcp"):
        return await call_next(request)
    if request.method == "OPTIONS":
        return await call_next(request)

    key = request.headers.get("X-Admin-Key", "")
    if not key:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            key = authorization[7:].strip()
    if not key:
        key = request.headers.get("X-API-Key", "")

    if not key or not hmac.compare_digest(key, cfg.admin_key):
        logger.warning(
            "mcp_auth_failed method=%s path=%s request_id=%s",
            request.method,
            request.url.path,
            get_request_id(request),
        )
        return _error_response(
            request,
            401,
            "mcp_unauthorized",
            "MCP requires the admin key. Provide it via X-Admin-Key or Authorization: Bearer header.",
        )

    from core.agent_safety import set_actor

    set_actor("env_admin")
    return await call_next(request)
