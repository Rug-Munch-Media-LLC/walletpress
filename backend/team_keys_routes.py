"""Team API key management (admin only).

Roles: admin > operator > viewer. Keys are persisted through KeyStore and each
create/revoke is written to the append-only audit log.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from core.audit import get_audit
from core.auth import get_key_store

router = APIRouter(prefix="/api/v1/team", tags=["team-keys"])

VALID_ROLES = ("admin", "operator", "viewer")


def _require_admin(request: Request):
    """Return the caller's APIKey or raise 403 unless it has the admin role."""
    caller = getattr(request.state, "api_key_obj", None)
    if not caller or caller.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return caller


@router.post(
    "/keys",
    summary="Create Team Key",
    description="Create a team API key with specific role and permissions.",
)
async def create_team_key(label: str, role: str = "operator", request: Request = None):
    """Create a team API key.

    Roles (hierarchy: admin > operator > viewer):
      admin    — full access, can manage keys
      operator — generate wallets, view vault
      viewer   — read-only access

    Keys are persisted to disk via KeyStore (survive restarts) and scoped to
    the caller's owner account. The raw key is returned exactly once.
    """
    caller = _require_admin(request)
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Invalid role. Must be admin, operator, or viewer.",
        )

    key_id, raw_key = get_key_store().create(
        label=label, role=role, owner=caller.owner or caller.id
    )
    get_audit().log(
        "team.key.create",
        actor=caller.id,
        resource=key_id,
        detail={"label": label, "role": role},
    )
    return {
        "key_id": key_id,
        "api_key": raw_key,
        "label": label,
        "role": role,
        "warning": "Save this key now. It won't be shown again.",
    }


@router.get(
    "/keys",
    summary="List Team Keys",
    description="List all team API keys.",
)
async def list_team_keys(request: Request):
    """List all team API keys (admin only)."""
    _require_admin(request)
    return {"keys": get_key_store().list()}


@router.delete(
    "/keys/{key_id}",
    summary="Revoke Team Key",
    description="Revoke a team API key immediately.",
)
async def revoke_team_key(key_id: str, request: Request):
    """Revoke a team API key immediately (admin only)."""
    caller = _require_admin(request)
    if not get_key_store().revoke(key_id):
        raise HTTPException(status_code=404, detail=f"Key {key_id} not found")
    get_audit().log("team.key.revoke", actor=caller.id, resource=key_id)
    return {"revoked": True, "key_id": key_id}
