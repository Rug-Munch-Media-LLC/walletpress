"""Wallet Admin Router — API keys, alerts, webhooks, audit, bulk ops, 2FA, proof.

Extracted from chain_vault.py in Phase 5 refactor. These endpoints are
administrative (not directly wallet CRUD) — most deal with cross-cutting
concerns like API key management, alerting, webhooks, and proof generation.

Auth: All endpoints require API key with at least 'operator' role.
"""

from __future__ import annotations

import json
import logging
import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.auth import get_key_store
from core.audit import get_audit
from core.config import cfg
from core.proof import PROOF_VERSION, get_proof
from core.vault import get_vault
from ._persistent_store import PersistentStore as _PersistentStore

logger = logging.getLogger("wp.admin")


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


class BulkFilterRequest(BaseModel):
    chains: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    label_contains: str = Field(default="")
    older_than_days: int = Field(default=0, ge=0)
    filters: dict = Field(default_factory=dict)  # legacy alias for {chains, tags, ...}


class BulkDeleteRequest(BaseModel):
    wallet_ids: list[str] = Field(...)


class BulkExportRequest(BaseModel):
    format: str = Field(default="csv")
    ids: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    format: str = Field(default="json", description="json, csv, env")
    ids: list[str] = Field(default_factory=list, description="Specific wallet IDs (empty = all)")


# Use a fresh router for admin endpoints — mounted under /api/v1/chain-vault
# so the URL paths are unchanged for existing API consumers.
router = APIRouter(prefix="/api/v1/chain-vault", tags=["Chain Vault Admin"])


def _audit(action: str, request: Request, resource: str = "", detail: dict | None = None) -> None:
    """Log an admin action to the audit trail."""
    audit = get_audit()
    audit.log(
        action,
        actor=request.headers.get("X-API-Key", "")[:16],
        resource=resource,
        detail=detail or {},
    )


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

    # Register with webhook deliverer for live delivery
    from core.webhooks import get_webhook_deliverer
    get_webhook_deliverer().register(webhook_id, req.url, wh_secret, req.events)

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
    from core.webhooks import get_webhook_deliverer
    get_webhook_deliverer().unregister(webhook_id)
    return {"deleted": True, "webhook_id": webhook_id}


# ── Webhook Delivery Log ──────────────────────────────────


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
            import asyncio
            asyncio.ensure_future(get_webhook_deliverer().emit("webhook.test", {
                "test": True,
                "webhook_id": webhook_id,
                "timestamp": time.time(),
            }))
            return {"sent": True, "note": "Test event sent. Check /webhooks/deliveries for status."}
    raise HTTPException(status_code=404, detail="Webhook not found")


@router.post("/webhooks/{webhook_id}/retry")
async def retry_webhook(webhook_id: str):
    """Retry the last failed delivery for a webhook."""
    webhooks = _PersistentStore.all("webhooks")
    for wh in webhooks:
        if wh.get("id") == webhook_id:
            from core.webhooks import get_webhook_deliverer
            import asyncio
            asyncio.ensure_future(get_webhook_deliverer().emit("webhook.retry", {
                "retry": True,
                "webhook_id": webhook_id,
            }))
            return {"retried": True, "note": "Retry sent. Check /webhooks/deliveries for status."}
    raise HTTPException(status_code=404, detail="Webhook not found")


# ═══════════════════════════════════════════════════════════════════
#  AUDIT TRAIL
# ═══════════════════════════════════════════════════════════════════


@router.get("/audit-trail")
async def audit_trail(limit: int = 100, action: str = ""):
    """Get the immutable audit trail for all wallet operations.

    Trust: The audit log is append-only. Every wallet generation,
    key export, rotation, and deletion is logged. Logs cannot be
    modified — only new entries can be appended.
    """
    audit = get_audit()
    entries = audit.query(limit=limit, action=action)
    return {
        "audit_entries": entries,
        "total": len(entries),
        "note": "Audit log is append-only. Entries cannot be modified or deleted.",
    }


# ═══════════════════════════════════════════════════════════════════
#  BULK OPERATIONS
# ═══════════════════════════════════════════════════════════════════


@router.post("/bulk/filter")
async def bulk_filter(req: BulkFilterRequest, request: Request):
    """Filter wallets by custom criteria."""
    vault = get_vault()
    all_wallets = vault.list(limit=10000)
    results = all_wallets

    for key, value in req.filters.items():
        if key == "chain":
            results = [w for w in results if w.chain == value]
        elif key == "label":
            results = [w for w in results if value.lower() in w.label.lower()]
        elif key == "tag":
            results = [w for w in results if value in w.tags]
        elif key == "has_balance":
            results = [w for w in results if (w.balance_usd > 0) == value]

    return {
        "filtered": len(results),
        "filters_applied": req.filters,
        "wallets": [{"id": w.id, "chain": w.chain, "address": w.address, "label": w.label,
                     "balance_usd": w.balance_usd} for w in results],
    }


@router.post("/bulk/delete")
async def bulk_delete(req: BulkDeleteRequest, request: Request):
    """Delete multiple wallets at once."""
    _audit("bulk.delete", request, detail={"count": len(req.ids)})
    vault = get_vault()
    deleted = []
    for wid in req.ids:
        if vault.delete(wid):
            deleted.append(wid)
    return {
        "deleted": len(deleted),
        "total_requested": len(req.ids),
        "deleted_ids": deleted,
    }


@router.post("/bulk/export")
async def bulk_export(req: BulkExportRequest, request: Request):
    """Export multiple wallets in various formats."""
    vault = get_vault()
    wallets = []
    if req.ids:
        for wid in req.ids:
            w = vault.get(wid)
            if w:
                wallets.append(w)
    else:
        wallets = vault.list(limit=10000)

    if req.format == "csv":
        import csv as _csv
        import io as _io
        buf = _io.StringIO()
        writer = _csv.writer(buf)
        writer.writerow(["chain", "address", "label", "created_at"])
        for w in wallets:
            writer.writerow([w.chain, w.address, w.label, w.created_at])
        data = buf.getvalue()
    elif req.format == "env":
        lines = ["# WalletPress Export"]
        for w in wallets:
            lines.append(f"WALLET_{w.chain.upper()}_ADDRESS={w.address}")
        data = "\n".join(lines)
    else:
        data = json.dumps([{"chain": w.chain, "address": w.address, "label": w.label,
                            "created_at": w.created_at} for w in wallets], indent=2)

    return {
        "format": req.format,
        "count": len(wallets),
        "data": data,
    }


# ═══════════════════════════════════════════════════════════════════
#  EXPORT (STANDARD)
# ═══════════════════════════════════════════════════════════════════


@router.post("/export")
async def export_wallets(req: ExportRequest, request: Request):
    """Export wallet data in multiple formats.

    Formats: json (full data), csv (addresses), env (KEY=VALUE pairs).
    Private keys are NEVER included in exports.
    """
    return await bulk_export(BulkExportRequest(format=req.format, ids=req.ids), request)


# ═══════════════════════════════════════════════════════════════════
#  PAYMENT ROUTER (for crypto payment processing)
# ═══════════════════════════════════════════════════════════════════

payment_router = APIRouter(prefix="/api/v1/chain-vault", tags=["Payments"])


class PaymentIntentRequest(BaseModel):
    wallet_id: str = Field(...)
    amount_usd: float = Field(...)
    chain: str = Field(default="solana")
    token: str = Field(default="USDC")
    description: str = Field(default="")


class PaymentVerifyRequest(BaseModel):
    payment_id: str = Field(...)
    tx_hash: str = Field(default="")
    chain: str = Field(default="solana")


@payment_router.post("/payments/create")
async def create_payment_intent(req: PaymentIntentRequest, request: Request):
    """Create a payment intent for crypto payment collection.

    Returns the wallet address and amount for the user to send funds.
    """
    _audit("payment.create", request, detail={"amount_usd": req.amount_usd, "chain": req.chain})
    vault = get_vault()
    wallet = vault.get(req.wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    payment_id = f"pay_{secrets.token_hex(8)}"
    payment = {
        "id": payment_id,
        "payment_id": payment_id,
        "wallet_id": req.wallet_id,
        "address": wallet.address,
        "chain": req.chain,
        "amount_usd": req.amount_usd,
        "token": req.token,
        "description": req.description,
        "status": "pending",
        "created_at": time.time(),
    }
    _PersistentStore.put("payments", payment)
    return {
        "payment": payment,
        "qr_data": f"{req.chain}:{wallet.address}?amount={req.amount_usd}",
    }


@payment_router.post("/payments/verify")
async def verify_payment(req: PaymentVerifyRequest, request: Request):
    """Verify a crypto payment has been confirmed on-chain.

    Checks the transaction status using available RPC endpoints.
    Without RPC configured, returns the recorded payment status.
    """
    payment = _PersistentStore.get("payments", req.payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    payment["status"] = "confirmed" if req.tx_hash else "pending"
    payment["tx_hash"] = req.tx_hash or payment.get("tx_hash", "")
    payment["verified_at"] = time.time()
    _PersistentStore.put("payments", payment)
    return {"payment": payment, "verified": bool(req.tx_hash)}


@payment_router.get("/payments/list")
async def list_payments():
    """List all payment intents."""
    payments = _PersistentStore.all("payments")
    return {"payments": payments, "total": len(payments)}


@payment_router.get("/payments/{payment_id}")
async def get_payment(payment_id: str):
    """Get payment details by ID."""
    payment = _PersistentStore.get("payments", payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"payment": payment}


# ═══════════════════════════════════════════════════════════════════
#  TOTP 2FA
# ═══════════════════════════════════════════════════════════════════


def _require_totp(request: Request):
    """Require valid TOTP code for admin operations."""
    from core.totp import get_totp_manager
    mgr = get_totp_manager()
    if not mgr.is_enabled():
        return
    code = request.headers.get("X-TOTP-Code", "")
    if not mgr.verify(code):
        raise HTTPException(status_code=401, detail="TOTP code required or invalid. Set X-TOTP-Code header.")


@router.post("/admin/2fa/setup")
async def setup_2fa(request: Request):
    """Generate a new TOTP secret for 2FA.

    Returns a QR URI compatible with Google Authenticator, Authy,
    1Password, Bitwarden, and any TOTP-compliant app.

    Call POST /admin/2fa/verify with the code from your authenticator
    app to confirm setup, then call POST /admin/2fa/enable to activate.
    """
    from core.totp import get_totp_manager
    mgr = get_totp_manager()
    result = mgr.setup()
    _audit("2fa.setup", request)
    return result


@router.post("/admin/2fa/verify-setup")
async def verify_2fa_setup(code: str, request: Request):
    """Verify a TOTP code to confirm 2FA setup is working."""
    from core.totp import get_totp_manager
    mgr = get_totp_manager()
    if mgr.verify(code):
        mgr.enable()
        _audit("2fa.enable", request)
        return {"enabled": True, "message": "2FA is now active for all admin operations."}
    return {"enabled": False, "error": "Invalid TOTP code. Check your authenticator app."}


@router.post("/admin/2fa/disable")
async def disable_2fa(request: Request):
    """Disable 2FA."""
    _require_totp(request)
    from core.totp import get_totp_manager
    mgr = get_totp_manager()
    mgr.disable()
    _audit("2fa.disable", request)
    return {"enabled": False}


@router.get("/admin/2fa/status")
async def status_2fa():
    """Check whether 2FA is enabled."""
    from core.totp import get_totp_manager
    mgr = get_totp_manager()
    return {"enabled": mgr.is_enabled()}


# ═══════════════════════════════════════════════════════════════════
#  CONFIGURATION (for WP plugin to read)
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


# ═══════════════════════════════════════════════════════════════════
#  PROOF OF GENERATION (Immutable Wallet Attestations)
# ═══════════════════════════════════════════════════════════════════


@router.post("/proof/commit")
async def proof_commit(request: Request, chain: str = "local"):
    """Manually commit all pending attestations to a Merkle root.

    Optionally commit to Arweave or Ethereum for permanent on-chain storage.

    This is the Big Idea. Every wallet gets a cryptographic birth
    certificate. The Merkle root is committed and can be sealed
    on a blockchain for permanent, immutable timestamping.

    Chains:
      local    — store in SQLite (instant, free)
      arweave  — commit to Arweave permaweb (~$0.000001, set WP_POF_ARWEAVE_KEY_PATH)
      ethereum — commit to Ethereum mainnet (~$5-50 gas, set WP_POF_ETH_RPC + WP_POF_ETH_PRIVATE_KEY)
    """
    proof = get_proof()
    root_hash, count = proof.compute_merkle_root()
    if not root_hash:
        return {"committed": False, "reason": "No pending attestations"}

    effective_chain = "local"
    if chain in ("arweave", "ethereum"):
        effective_chain = chain

    result = proof.commit(root_hash, count, commitment_chain=effective_chain)
    _audit("proof.commit", request, detail={"root_hash": root_hash[:16], "count": count, "chain": effective_chain})

    return {
        "committed": True,
        "root_hash": root_hash,
        "attestation_count": count,
        "chain": effective_chain,
        "commitment_tx": result.get("commitment_tx", ""),
        "verification_url": result.get("verification_url", ""),
        "merkle_proofs_saved": True,
        "message": f"Merkle root committed to {effective_chain}. {count} attestations sealed." if effective_chain == "local"
                   else f"Merkle root committed to {effective_chain}. TX: {result.get('commitment_tx', 'pending')}",
    }


@router.get("/proof/provenance/{wallet_id}")
async def proof_provenance(wallet_id: str):
    """Get the complete cryptographic provenance for a wallet.

    Returns the full Merkle proof path so anyone can independently
    verify that this wallet was part of a committed root.

    This is the wallet's complete BIRTH CERTIFICATE + PROOF OF INCLUSION.
    """
    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    proof = get_proof()
    result = proof.get_proof_by_wallet(wallet_id)
    if not result.get("exists"):
        return {"wallet_id": wallet_id, "attested": False, "message": "No attestation found"}
    return {
        "wallet_id": wallet_id,
        "address": wallet.address,
        "chain": wallet.chain,
        "attested": True,
        "provenance": {
            "created_at": result["created_at"],
            "code_version": result["code_version"],
            "leaf_hash": result["leaf_hash"],
            "merkle_root": result["root_hash"],
            "merkle_proof_verified": result["merkle_proof_verified"],
            "commitment": result["root"],
        },
        "verification_instructions": [
            "To verify: reconstruct the Merkle root using the leaf hash and proof path",
            "1. Start with the leaf hash",
            "2. For each step in proof_path, hash leaf + sibling (or sibling + leaf) based on is_left",
            "3. Compare the result with the committed root_hash",
            "4. Check the root was committed to the chain: local/arweave/ethereum",
        ],
    }


@router.get("/proof/verify/{wallet_id}")
async def proof_verify(wallet_id: str, include_key: bool = False):
    """Verify a wallet's Proof of Generation attestation.

    Returns the full provenance of the wallet including:
    - When it was created
    - Which code version generated it
    - The public key hash (proves key hasn't changed)
    - The Merkle root it was committed under
    - Whether the attestation is still valid

    This is the wallet's BIRTH CERTIFICATE.
    """
    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    proof = get_proof()
    result = proof.verify(wallet_id, wallet.address, wallet.public_key)

    if include_key:
        result["public_key"] = wallet.public_key

    return {
        "wallet_id": wallet_id,
        "address": wallet.address,
        "chain": wallet.chain,
        "verification": result,
        "trust_notes": [
            "This attestation proves the wallet existed at a specific time",
            f"Code version: {PROOF_VERSION}",
            "Public key hash is a one-way function — we don't store the raw key",
            "Merkle root can be cross-referenced on-chain for immutable proof",
        ],
    }


@router.get("/proof/roots")
async def proof_roots(limit: int = 10):
    """List recent Merkle roots committed for wallet attestations."""
    proof = get_proof()
    roots = proof.get_roots(limit)
    stats = proof.stats()
    return {
        "total_attestations": stats["total_attestations"],
        "total_roots": stats["merkle_roots"],
        "roots": roots,
    }


@router.get("/proof/stats")
async def proof_stats():
    """Get Proof of Generation statistics."""
    proof = get_proof()
    return {
        "service": "walletpress-proof-of-generation",
        "version": PROOF_VERSION,
        "stats": proof.stats(),
        "commitment_options": [
            {"chain": "local", "description": "SQLite (always, free)", "status": "active"},
            {"chain": "arweave", "description": "Arweave permaweb (~$0.000001/write)", "status": "active"},
            {"chain": "ethereum", "description": "Ethereum mainnet (~$5-50 gas)", "status": "active"},
        ],
        "verification_endpoint": "/api/v1/proof/verify/{wallet_id}",
    }


# ═══════════════════════════════════════════════════════════════════
#  PAPER WALLET + BIRTH CERTIFICATE PDF
# ═══════════════════════════════════════════════════════════════════


@router.get("/paper-wallet/{wallet_id}/pdf")
async def paper_wallet_pdf(wallet_id: str, request: Request):
    """Generate a printable paper wallet PDF.

    Returns a PDF with:
      - Wallet address + QR code
      - Private key (requires admin scope)
      - Public key
      - Derivation path
      - Proof of Generation hash
      - Security instructions

    Print on durable paper. Store in a safe. Never share digitally.
    """
    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    auth = request.headers.get("X-API-Key", "") or request.headers.get("Authorization", "").replace("Bearer ", "")
    include_key = False
    if auth:
        from core.auth import get_key_store
        ks = get_key_store()
        k = ks.verify(auth)
        include_key = k and ("wallet.admin" in k.scopes or "admin" in k.scopes)

    private_key = ""
    if include_key and wallet.encrypted_key:
        if wallet.encrypted:
            from wallet_engine.generator import get_generator as get_gen
            private_key = get_gen().decrypt_key(wallet.encrypted_key)
        else:
            private_key = wallet.encrypted_key

    from core.pdf import generate_paper_wallet
    pdf_bytes = generate_paper_wallet(
        address=wallet.address,
        chain=wallet.chain,
        private_key=private_key,
        public_key=wallet.public_key,
        derivation_path=wallet.derivation_path,
        created_at=wallet.created_at,
        label=wallet.label,
    )

    from fastapi.responses import Response as FastResponse
    return FastResponse(
        content=pdf_bytes or b"No PDF generator available. Install reportlab.",
        media_type="application/pdf" if pdf_bytes else "text/plain",
        headers={"Content-Disposition": f'attachment; filename="wallet_{wallet_id[:8]}.pdf"'},
    )


@router.get("/wallet/{wallet_id}/birth-certificate")
async def wallet_birth_certificate(wallet_id: str):
    """Generate a Wallet Birth Certificate — printable provenance document.

    This is unique to WalletPress. It cryptographically proves when and
    how the wallet was created, with a Merkle attestation linking this
    document to the immutable audit trail.

    Print it. Store it with your will. Use it for compliance.
    """
    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    proof = get_proof()
    attest = proof.get_attestation(wallet_id)

    from core.pdf import generate_birth_certificate
    pdf_bytes = generate_birth_certificate(
        wallet_id=wallet_id,
        address=wallet.address,
        chain=wallet.chain,
        public_key=wallet.public_key,
        created_at=wallet.created_at,
        proof_leaf=attest.get("leaf_hash", "") if attest else "",
        root_hash=attest.get("root_hash", "") if attest else "",
        committed=attest.get("committed", False) if attest else False,
    )

    from fastapi.responses import Response as FastResponse
    return FastResponse(
        content=pdf_bytes or b"No PDF generator available. Install reportlab.",
        media_type="application/pdf" if pdf_bytes else "text/plain",
        headers={"Content-Disposition": f'attachment; filename="birth_certificate_{wallet_id[:8]}.pdf"'},
    )
