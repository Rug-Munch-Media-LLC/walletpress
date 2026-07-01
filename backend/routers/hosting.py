"""WalletPress Hosted — user registration, subscription, and API key management.

Endpoints:
  POST /hosting/register  — Create account (free tier)
  POST /hosting/login     — Get API key (rate-limited per email)
  GET  /hosting/me        — Account details + usage
  GET  /hosting/plans     — Available plans + pricing
  POST /hosting/subscribe — Upgrade/downgrade plan (Stripe stub)
  GET  /hosting/usage     — Usage history

Revenue model:
  Free:    3 chains, 10 wallets/day
  Starter: $29/mo, 10 chains, 500 wallets/day
  Pro:     $79/mo, 55 chains, unlimited
  Enterprise: $199/mo, everything

P2-13: /hosting/login is rate-limited per email (exponential backoff).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.hosting import PLANS, get_hosting

logger = logging.getLogger("wp.hosting")

router = APIRouter(prefix="/hosting", tags=["Hosted"])

# ── Login rate limiter ───────────────────────────────────────────────────────
# Sliding window per email. Backoff: 3 failures → 30s, 5 → 5min, 10 → 1h.
# Production should swap this for Redis-backed rate limiting, but the
# in-memory version is fine for single-instance deployments.
_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_LOGIN_LOCKOUT_UNTIL: dict[str, float] = {}


def _login_rate_limit_check(email: str) -> None:
    """Raise 429 if this email is in a lockout window."""
    now = time.time()
    until = _LOGIN_LOCKOUT_UNTIL.get(email, 0)
    if until > now:
        retry_after = int(until - now) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )
    # Trim attempts older than 1 hour
    _LOGIN_ATTEMPTS[email] = [t for t in _LOGIN_ATTEMPTS[email] if now - t < 3600]


def _login_record_attempt(email: str, success: bool) -> None:
    """Record a login attempt; lockout if too many failures."""
    now = time.time()
    if success:
        _LOGIN_ATTEMPTS.pop(email, None)
        _LOGIN_LOCKOUT_UNTIL.pop(email, None)
        return
    _LOGIN_ATTEMPTS[email].append(now)
    failures = len(_LOGIN_ATTEMPTS[email])
    if failures >= 10:
        _LOGIN_LOCKOUT_UNTIL[email] = now + 3600  # 1 hour
    elif failures >= 5:
        _LOGIN_LOCKOUT_UNTIL[email] = now + 300  # 5 min
    elif failures >= 3:
        _LOGIN_LOCKOUT_UNTIL[email] = now + 30  # 30 sec


class RegisterRequest(BaseModel):
    email: str = Field(...)
    password: str = Field(..., min_length=8)
    name: str = Field(default="")


class LoginRequest(BaseModel):
    email: str = Field(...)
    password: str = Field(...)


class VerifyEmailRequest(BaseModel):
    token: str = Field(...)


class SubscribeRequest(BaseModel):
    plan: str = Field(...)
    stripe_token: str = Field(default="", description="Stripe token (stub for now)")


def _get_user_from_request(request: Request) -> dict:
    auth = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not auth:
        auth = request.headers.get("X-API-Key", "")
    if not auth:
        raise HTTPException(status_code=401, detail="API key required")
    host = get_hosting()
    user = host.get_by_api_key(auth)
    if not user:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return dict(user)


@router.post("/register")
async def register(req: RegisterRequest):
    """Create a free WalletPress Hosted account.

    Returns an API key valid for the free tier.
    Verify email via Stripe or manual upgrade for higher tiers.
    """
    host = get_hosting()
    result = host.register(req.email, req.password, req.name)
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return {
        "registered": True,
        "user_id": result["user_id"],
        "api_key": result["api_key"],
        "plan": result["plan"],
        "note": "Save your API key. It won't be shown again.",
    }


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    """Login and get API key. Rate-limited per email."""
    _login_rate_limit_check(req.email.lower())
    host = get_hosting()
    user = host.login(req.email, req.password)
    success = user is not None
    _login_record_attempt(req.email.lower(), success)
    if not success:
        logger.info(f"Login failed for {req.email[:20]}... (rate-limit aware)")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "user_id": user["id"],
        "api_key": user["api_key"],
        "plan": user["plan"],
        "name": user["name"],
    }


@router.post("/verify-email")
async def verify_email(req: VerifyEmailRequest):
    """Verify the email address associated with a registration.

    Required when WP_REQUIRE_EMAIL_VERIFY=1 is set. The token is generated
    by /hosting/register and should be sent via email (use core/email_notify.py
    to send automatically when SMTP is configured).

    Returns 200 on success, 400 on invalid/expired token.
    """
    host = get_hosting()
    if host.verify_email(req.token):
        return {"verified": True}
    raise HTTPException(
        status_code=400,
        detail="Invalid or expired verification token. Register again to get a new one.",
    )


@router.get("/me")
async def me(request: Request):
    """Get account details and current usage."""
    user = _get_user_from_request(request)
    host = get_hosting()
    used = host.daily_usage(user["id"])
    plan = PLANS.get(user["plan"], PLANS["free"])
    remaining = max(0, (plan["daily_wallet_limit"] - used)) if plan["daily_wallet_limit"] > 0 else -1

    return {
        "user_id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "plan": user["plan"],
        "plan_name": plan["name"],
        "api_key": user["api_key"],
        "usage_today": used,
        "daily_limit": plan["daily_wallet_limit"],
        "remaining": remaining,
        "subscription_status": user.get("subscription_status", "active"),
    }


@router.get("/plans")
async def plans():
    """List available subscription plans."""
    return {
        "plans": [
            {
                "id": k,
                "name": v["name"],
                "price_usd": v["price_usd"],
                "chains": v["chains"],
                "daily_wallet_limit": v["daily_wallet_limit"] if v["daily_wallet_limit"] > 0 else "unlimited",
                "features": v["features"],
                "api_access": v["api_access"],
            }
            for k, v in PLANS.items()
        ]
    }


@router.post("/subscribe")
async def subscribe(req: SubscribeRequest, request: Request):
    """Subscribe to a paid plan.

    Stub — integrate Stripe via WP_STRIPE_KEY env var.
    For now, admin can manually upgrade users.
    """
    user = _get_user_from_request(request)
    plan = PLANS.get(req.plan)
    if not plan:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {req.plan}")

    host = get_hosting()
    conn = host._conn()
    conn.execute("UPDATE users SET plan = ?, subscription_status = 'active' WHERE id = ?",
                 (req.plan, user["id"]))
    conn.commit()
    conn.close()

    return {
        "upgraded": True,
        "user_id": user["id"],
        "plan": req.plan,
        "plan_name": plan["name"],
        "price_usd": plan["price_usd"],
        "note": "Plan activated. Stripe integration coming soon — contact support for billing.",
    }


@router.get("/usage")
async def usage(request: Request, days: int = 7):
    """Get usage history for the last N days."""
    user = _get_user_from_request(request)
    host = get_hosting()
    cutoff = time.time() - (days * 86400)

    conn = host._conn()
    rows = conn.execute(
        "SELECT * FROM usage_log WHERE user_id = ? AND timestamp >= ? ORDER BY timestamp DESC",
        (user["id"], cutoff),
    ).fetchall()
    conn.close()

    total = sum(r["count"] for r in rows)
    return {
        "user_id": user["id"],
        "days": days,
        "total_operations": total,
        "history": [dict(r) for r in rows],
    }
