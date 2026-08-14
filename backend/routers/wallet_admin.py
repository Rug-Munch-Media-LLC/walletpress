"""Wallet Admin Router — Educational OSS example of an admin API.

THIS IS A STRIPPED EDUCATIONAL EXAMPLE.
The full production version includes TOTP 2FA, SHA-256 chained audit logs,
Merkle proof attestation, bulk operations, paper wallet PDF generation,
birth certificates, payment processing, and more.

This file shows the PATTERN: how to build admin endpoints for API keys,
webhooks, alerts, and configuration. Replace the stores with your own.

Auth: All endpoints require API key with at least 'operator' role.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.audit import get_audit
from core.auth import get_key_store
from core.config import cfg

from ._persistent_store import PersistentStore as _PersistentStore

logger = logging.getLogger("wp.admin")

# Fire-and-forget background tasks (e.g. webhook emissions) kept alive so the
# event loop doesn't garbage-collect them mid-flight.
_background_tasks: set[asyncio.Task] = set()


class APIKeyCreateRequest(BaseModel):
    label: str = Field(...)
    scopes: list[str] = Field(default=["vault.read"])


class AlertCreateRequest(BaseModel):
    wallet_id: str = Field(...)
    alert_type: str = Field(default="balance_change")
    threshold_usd: float = Field(default=0.0)
    channel: str = Field(default="webhook")
    config: dict = Field(default_factory=dict)


class AlertDeleteRequest(BaseModel):
    alert_id: str = Field(...)


class WebhookCreateRequest(BaseModel):
    url: str = Field(...)
    events: list[str] = Field(default_factory=lambda: ["wallet.generated"])
    secret: str = Field(default="")
    active: bool = Field(default=True)


router = APIRouter(prefix="/api/v1/chain-vault", tags=["Chain Vault Admin"])


def _audit(action: str, request: Request, resource: str = "", detail: dict | None = None) -> None:
    """Log an admin action to the audit trail."""
    get_audit().log(
        action,
        actor=request.headers.get("X-API-Key", "")[:16] or "anonymous",
        resource=resource,
        detail=detail or {},
    )


# ═══════════════════════════════════════════════════════════════════
#  API KEYS
# ═══════════════════════════════════════════════════════════════════


@router.post("/api-keys")
async def create_api_key(req: APIKeyCreateRequest, request: Request):
    """Create a new API key for programmatic access."""
    _audit("api_key.create", request, detail={"label": req.label, "scopes": req.scopes})
    ks = get_key_store()
    key_id, raw_key = ks.create(req.label, req.scopes)
    return {
        "api_key_id": key_id,
        "api_key": raw_key,
        "label": req.label,
        "scopes": req.scopes,
        "warning": "Save this key now. It will not be shown again.",
    }


@router.get("/api-keys")
async def list_api_keys(request: Request):
    """List all API keys (masked, keys not shown)."""
    ks = get_key_store()
    return {"api_keys": ks.list(), "note": "Full keys only shown once at creation."}


@router.post("/api-keys/revoke")
async def revoke_api_key(req: APIKeyCreateRequest, request: Request):
    """Revoke an API key immediately."""
    _audit("api_key.revoke", request, resource=req.label)
    ks = get_key_store()
    ks.revoke(req.label)
    return {"revoked": True, "key_id": req.label}


# ═══════════════════════════════════════════════════════════════════
#  ALERTS
# ═══════════════════════════════════════════════════════════════════


@router.post("/alerts")
async def create_alert(req: AlertCreateRequest, request: Request):
    """Create a wallet alert for balance changes or on-chain events."""
    _audit("alert.create", request, detail={"type": req.alert_type, "wallet": req.wallet_id})
    alert_id = f"alert_{secrets.token_hex(4)}"
    alert = {
        "id": alert_id,
        "wallet_id": req.wallet_id,
        "type": req.alert_type,
        "threshold_usd": req.threshold_usd,
        "channel": req.channel,
        "config": req.config,
        "created_at": time.time(),
        "active": True,
    }
    _PersistentStore.put("alerts", alert)
    return {"alert_id": alert_id, **alert}


@router.get("/alerts")
async def list_alerts():
    """List all configured alerts."""
    alerts = _PersistentStore.all("alerts")
    return {"alerts": alerts, "total": len(alerts)}


@router.post("/alerts/delete")
async def delete_alert(req: AlertDeleteRequest):
    """Delete an alert."""
    _PersistentStore.delete("alerts", req.alert_id)
    return {"deleted": True, "alert_id": req.alert_id}


# ═══════════════════════════════════════════════════════════════════
#  WEBHOOKS
# ═══════════════════════════════════════════════════════════════════


@router.post("/webhooks")
async def create_webhook(req: WebhookCreateRequest, request: Request):
    """Create a webhook for wallet events.

    Events: wallet.generated, payment.received, gate.accessed,
    alert.triggered, wallet.rotated, wallet.swept
    """
    _audit("webhook.create", request, detail={"events": req.events})
    webhook_id = f"wh_{secrets.token_hex(4)}"
    wh_secret = req.secret or secrets.token_hex(16)
    wh = {
        "id": webhook_id,
        "url": req.url,
        "events": req.events,
        "secret": wh_secret,
        "created_at": time.time(),
        "active": True,
    }
    _PersistentStore.put("webhooks", wh)
    return {"webhook_id": webhook_id, **wh}


@router.get("/webhooks")
async def list_webhooks():
    """List all configured webhooks."""
    webhooks = _PersistentStore.all("webhooks")
    return {"webhooks": webhooks, "total": len(webhooks)}


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str):
    """Delete a webhook."""
    _PersistentStore.delete("webhooks", webhook_id)
    return {"deleted": True, "webhook_id": webhook_id}


@router.get("/webhooks/deliveries")
async def webhook_deliveries(limit: int = 50):
    """View recent webhook delivery attempts with status and response codes."""
    from core.webhooks import delivery_log

    return {"deliveries": list(reversed(delivery_log))[:limit], "total": len(delivery_log)}


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: str):
    """Send a test event to verify webhook endpoint is working."""
    webhooks = _PersistentStore.all("webhooks")
    for wh in webhooks:
        if wh.get("id") == webhook_id:
            from core.webhooks import get_webhook_deliverer

            task = asyncio.ensure_future(
                get_webhook_deliverer().emit(
                    "webhook.test",
                    {
                        "test": True,
                        "webhook_id": webhook_id,
                        "timestamp": time.time(),
                    },
                )
            )
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
            return {"sent": True, "note": "Test event sent. Check /webhooks/deliveries for status."}
    raise HTTPException(status_code=404, detail="Webhook not found")


# ═══════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════


@router.get("/config")
async def get_config():
    """Get WalletPress backend configuration and capabilities."""
    return {
        "version": cfg.version,
        "features": {
            "client_side_generation": True,
            "server_side_generation": True,
            "encrypted_vault": bool(cfg.vault_password),
            "rate_limiting": cfg.rate_limit_per_minute > 0,
            "audit_logging": True,
            "api_key_auth": True,
            "telemetry": False,
            "open_source": True,
        },
        "standards": ["BIP39", "BIP32", "BIP44", "BIP49", "BIP84"],
        "encryption": "AES-256-GCM + Argon2id" if cfg.vault_password else "plaintext",
        "max_batch_size": cfg.max_wallets_per_request,
        "proof_of_generation": True,
    }
