"""WalletPress Backend — Multi-Chain Wallet Generation & Management.

Usage:
    # Install and run (no Docker needed)
    pip install -r requirements.txt
    uvicorn main:app --port 8010

    # Or via the walletpress CLI
    python main.py

    # With Docker
    docker compose up

Trust: This backend is fully open source. You can verify every operation.
Private keys are encrypted at rest with AES-256-GCM + Argon2id. The vault
password is configurable and NEVER logged.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# AI Wallet Agent
from agent.mcp_server import mcp as agent_mcp
from agent.scheduler import scheduler as agent_scheduler
from core.audit import get_audit
from core.auth import get_key_store
from core.config import cfg
from core.ip_allowlist import IPAllowlistMiddleware
from core.jwt_auth import JWTValidationMiddleware
from core.license_check import LicenseMiddleware
from core.rate_limit import RateLimitMiddleware
from core.webhooks import get_webhook_deliverer
from routers import (
    airdrop as airdrop_router,
    chain_vault,
    health_monitor as health_router,
    hosting as hosting_router,
    license_router as license_router,
    metrics as metrics_router,
    retention as retention_router,
    test_vectors,
    wallet_admin,
    wallet_analysis,
    wallet_memory,
)
from x402_service import app as x402_app

logger = logging.getLogger("wp")


class RequestIDMiddleware:
    """Generates X-Request-ID, stamps it on request.state and response headers.

    Must be the outermost middleware so every downstream handler and log
    line can reference the request_id.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())[:12]

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                headers.append((b"X-Request-ID", request_id.encode()))
                message["headers"] = headers
            await send(message)

        scope["state"] = {**scope.get("state", {}), "request_id": request_id}
        await self.app(scope, receive, send_with_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"WalletPress v{cfg.version} starting on {cfg.host}:{cfg.port}")

    if not cfg.admin_key:
        raise RuntimeError("WP_ADMIN_KEY is required. Set it in the environment before starting.")
    if not cfg._vault_password:
        raise RuntimeError(
            "WP_VAULT_PASSWORD is required. Set it in the environment before starting."
        )

    os.makedirs(cfg.data_dir, exist_ok=True)

    # Print AI provider table on startup
    from agent.providers import list_providers

    for line in list_providers().split("\n"):
        logger.info(line)

    # Log referral revenue status
    from plugins.defi import REF_HYPERLIQUID_WALLET, REF_JUPITER_WALLET, REVENUE_MODE

    jup_ok = bool(REF_JUPITER_WALLET)
    hl_ok = bool(REF_HYPERLIQUID_WALLET)
    logger.info(
        f"Revenue mode: {REVENUE_MODE.upper()} | Jupiter: {'READY (50bps)' if jup_ok else 'NEEDS SETUP'} | Hyperliquid: {'READY (builder code)' if hl_ok else 'NEEDS SETUP'}"
    )
    if REVENUE_MODE == "freemium":
        logger.info(
            "Revenue: Jupiter 50bps (set WP_REF_JUPITER_WALLET) + Hyperliquid builder fees (set WP_REF_HYPERLIQUID_WALLET, needs 100 USDC perps)"
        )
    else:
        logger.info("Self-referral mode: you keep 100% of platform revenue.")

    # Initialize services into app.state (enables DI and testability)
    from core.audit import AuditLog
    from core.auth import KeyStore
    from core.license import LicenseManager
    from core.proof import ProofOfGeneration
    from core.vault import Vault
    from wallet_engine.generator import WalletGenerator

    app.state.vault = Vault(cfg.db_path)
    app.state.key_store = KeyStore(cfg.keys_path)
    app.state.audit = AuditLog(cfg.audit_path)
    app.state.license = LicenseManager()
    app.state.proof = ProofOfGeneration(cfg.data_dir / "proof.db")
    app.state.generator = WalletGenerator(vault_password=cfg.vault_password)
    app.state.webhook_deliverer = get_webhook_deliverer()
    await app.state.webhook_deliverer.start()

    # Reload persisted webhooks into the live deliverer
    from routers._persistent_store import PersistentStore

    PersistentStore.reload_webhooks()

    # Anchor source commit to Arweave for on-chain code verification
    if os.getenv("WP_POF_ARWEAVE_KEY_PATH"):
        from core.proof import anchor_source_commit

        result = anchor_source_commit()
        if result.get("anchored"):
            logger.info(
                f"Source commit anchored: {result['commit'][:16]}... tx={result.get('tx_id', '')}"
            )
        else:
            logger.warning(f"Source commit anchoring skipped: {result.get('reason', 'unknown')}")

    # Background tasks
    import asyncio

    # Start AI Agent background scheduler (DCA, monitoring, rotations)
    agent_scheduler.start()
    logger.info("AI Wallet Agent scheduler started")

    # Start Proof of Generation auto-commit background task
    async def proof_auto_commit_loop():
        auto_commit = os.getenv("WP_POF_AUTO_COMMIT", "1") == "1"
        if not auto_commit:
            logger.info("Proof of Generation auto-commit disabled (WP_POF_AUTO_COMMIT=0)")
            return
        interval = int(os.getenv("WP_POF_COMMIT_INTERVAL", "3600"))
        await asyncio.sleep(interval)  # delay first commit to let wallets accumulate
        while True:
            try:
                from core.proof import get_proof

                proof = get_proof()
                root_hash, count = proof.compute_merkle_root()
                if root_hash:
                    chain = "local"
                    if os.getenv("WP_POF_ARWEAVE_KEY_PATH"):
                        chain = "arweave"
                    elif os.getenv("WP_POF_ETH_RPC") and os.getenv("WP_POF_ETH_PRIVATE_KEY"):
                        chain = "ethereum"
                    proof.commit(root_hash, count, commitment_chain=chain)
                    logger.info(
                        f"Auto-committed {count} attestations to {chain}: {root_hash[:16]}..."
                    )
            except Exception as e:
                logger.error(f"Proof auto-commit failed: {e}")
            await asyncio.sleep(interval)

    app.state.proof_commit_task = asyncio.ensure_future(proof_auto_commit_loop())

    async def temporal_cleanup_loop():
        while True:
            await asyncio.sleep(60)
            try:
                from routers.chain_vault import _cleanup_expired_temporals

                _cleanup_expired_temporals()
            except Exception as e:
                logger.error(f"Temporal cleanup failed: {e}")

    app.state.temporal_cleanup_task = asyncio.ensure_future(temporal_cleanup_loop())

    yield

    agent_scheduler.stop()
    await app.state.webhook_deliverer.stop()
    logger.info("WalletPress shutdown complete")


app = FastAPI(
    title=cfg.title,
    version=cfg.version,
    description=cfg.description,
    lifespan=lifespan,
)


# ── Structured JSON logging (structlog) ─────────────────────────
from core.structured_logging import setup_logging as _setup_logging

_setup_logging(os.getenv("WP_LOG_LEVEL", "INFO"))

app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.cors_origins,
    allow_origin_regex=r"https://.*\.rugmunch\.io",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if cfg.rate_limit_per_minute > 0:
    app.add_middleware(RateLimitMiddleware, rate=cfg.rate_limit_per_minute)

app.add_middleware(metrics_router.MetricsMiddleware)


@app.middleware("http")
async def enforce_json_content_type(request: Request, call_next):
    """PEN-TEST: Reject non-JSON Content-Type on write endpoints.

    POST/PUT/PATCH/DELETE must use application/json (file uploads via multipart exempted).
    Prevents content-type smuggling and bypass of JSON validation.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        path = request.url.path
        exempt = ("/health", "/docs", "/openapi.json", "/metrics", "/mcp/", "/ws/")
        if not path.startswith(exempt):
            ct = (request.headers.get("content-type") or "").lower().strip()
            if (
                ct
                and not ct.startswith("application/json")
                and not ct.startswith("multipart/form-data")
            ):
                return JSONResponse(
                    status_code=415,
                    content={
                        "detail": "Unsupported media type. Use Content-Type: application/json.",
                        "code": "unsupported_media_type",
                    },
                )
    return await call_next(request)


app.add_middleware(JWTValidationMiddleware)
app.add_middleware(IPAllowlistMiddleware)
app.add_middleware(LicenseMiddleware)


@app.middleware("http")
async def require_auth_on_mutations(request: Request, call_next):
    """Authenticate + role-check ALL requests.

    P0-3 fix: previously this middleware only checked key validity, not role.
    A 'viewer' role key could mutate state. Now we:
      1. Verify the key (or accept admin key)
      2. Attach the APIKey to request.state.api_key_obj
      3. Enforce minimum role 'operator' on write endpoints (callers needing
         stricter checks use the require_role() dependency)

    Audit fix (2026-09-06): authentication is now required on ALL endpoints
    (GET included). Previously GET requests to vault/retention endpoints were
    exempt, letting unauthenticated callers read wallet metadata and trigger
    key-returning flows. Only the explicit public skip-list below is exempt.
    Unauthenticated callers are rejected with 401 BEFORE any handler runs,
    so no key material can leave the process without a valid credential.
    """
    path = request.url.path
    skip = ("/health", "/docs", "/openapi.json", "/metrics", "/hosting/register", "/hosting/login")

    needs_auth = not path.startswith((*skip, "/mcp/", "/ws/"))

    if needs_auth:
        auth = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not auth:
            auth = request.headers.get("X-API-Key", "")
        if not auth:
            return JSONResponse(
                status_code=401,
                content={
                    "type": "/errors/unauthorized",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "API key required. Provide via X-API-Key or Authorization: Bearer header.",
                    "request_id": getattr(request.state, "request_id", ""),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "code": "unauthorized",
                },
            )

        api_key_obj = None
        if auth == cfg.admin_key:
            # Admin env-var key gets implicit admin role
            from core.auth import APIKey

            api_key_obj = APIKey(
                id="env_admin",
                key_hash="env",
                label="env_admin",
                scopes=["admin"],
                created_at=0,
                role="admin",
            )
        else:
            from core.auth import get_key_store

            ks = get_key_store()
            api_key_obj = ks.verify(auth)
            if not api_key_obj:
                return JSONResponse(
                    status_code=403,
                    content={
                        "type": "/errors/forbidden",
                        "title": "Forbidden",
                        "status": 403,
                        "detail": "Invalid or revoked API key",
                        "request_id": getattr(request.state, "request_id", ""),
                        "timestamp": datetime.now(UTC).isoformat(),
                        "code": "forbidden",
                    },
                )

        # For write requests: viewer is not enough
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            from core.auth import role_has_at_least

            if not role_has_at_least(api_key_obj.role, "operator"):
                return JSONResponse(
                    status_code=403,
                    content={
                        "type": "/errors/forbidden",
                        "title": "Forbidden",
                        "status": 403,
                        "detail": f"Insufficient role: '{api_key_obj.role}' cannot perform write operations. Required: operator or admin.",
                        "request_id": getattr(request.state, "request_id", ""),
                        "timestamp": datetime.now(UTC).isoformat(),
                        "code": "forbidden",
                    },
                )

        # Stash for endpoint handlers (and downstream dependencies)
        request.state.api_key_obj = api_key_obj
    response = await call_next(request)
    return response


@app.middleware("http")
async def require_admin_key_on_mcp(request: Request, call_next):
    """Require WP_ADMIN_KEY on every /mcp route.

    The AI Wallet Agent MCP server can decrypt private keys (vault_get with
    include_private_key), sweep wallets, and broadcast transactions. It was
    previously exempted from authentication in require_auth_on_mutations
    (which skipped /mcp/), allowing any unauthenticated caller to drain all
    wallets — including via agent_confirm, which self-approved any caller.

    All /mcp routes now require the admin key, accepted via:
      - X-Admin-Key header
      - Authorization: Bearer <key>
      - X-API-Key header
    Comparison is constant-time (hmac.compare_digest). On success the
    authenticated actor is recorded in the asyncio context so the HITL
    confirmation flow (core.agent_safety) binds confirmations to the
    actor that initiated the action.

    CORS preflight (OPTIONS) is skipped so browsers can negotiate the
    X-Admin-Key custom header.
    """
    path = request.url.path
    if not path.startswith("/mcp"):
        return await call_next(request)

    if request.method == "OPTIONS":
        return await call_next(request)

    key = request.headers.get("X-Admin-Key", "")
    if not key:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            key = auth[7:].strip()
    if not key:
        key = request.headers.get("X-API-Key", "")

    if not key or not hmac.compare_digest(key, cfg.admin_key):
        logger.warning(
            "mcp_auth_failed method=%s path=%s request_id=%s",
            request.method,
            path,
            getattr(request.state, "request_id", "-"),
        )
        return JSONResponse(
            status_code=401,
            content={
                "type": "/errors/unauthorized",
                "title": "Unauthorized",
                "status": 401,
                "detail": "MCP requires the admin key. Provide it via X-Admin-Key or Authorization: Bearer header.",
                "request_id": getattr(request.state, "request_id", ""),
                "timestamp": datetime.now(UTC).isoformat(),
                "code": "mcp_unauthorized",
            },
        )

    # Bind the authenticated actor for HITL confirmations (agent_safety)
    from core.agent_safety import set_actor

    set_actor("env_admin")
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    rid = getattr(request.state, "request_id", "-")
    response = await call_next(request)
    elapsed = time.time() - start
    logger.info(
        "http_request method=%s path=%s status=%d elapsed=%.3fs request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
        rid,
    )
    return response


from fastapi.exceptions import HTTPException as FastAPIHTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


@app.exception_handler(StarletteHTTPException)
@app.exception_handler(FastAPIHTTPException)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    rid = _request_id(request)
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    status = exc.status_code
    return JSONResponse(
        status_code=status,
        content={
            "type": "about:blank",
            "title": {
                400: "Bad Request",
                401: "Unauthorized",
                403: "Forbidden",
                404: "Not Found",
                409: "Conflict",
                422: "Unprocessable Entity",
                429: "Too Many Requests",
                500: "Internal Server Error",
                502: "Bad Gateway",
                503: "Service Unavailable",
            }.get(status, "Error"),
            "status": status,
            "detail": detail,
            "request_id": rid,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    rid = _request_id(request)
    if isinstance(exc, (HTTPException, FastAPIHTTPException, StarletteHTTPException)):
        return await http_exception_handler(request, exc)
    logger.error(
        "unhandled_exception method=%s path=%s exc=%s request_id=%s",
        request.method,
        request.url.path,
        f"{type(exc).__name__}: {exc}",
        rid,
    )
    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "Internal server error",
            "request_id": rid,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


app.include_router(chain_vault.router)
app.include_router(wallet_admin.router)
app.include_router(wallet_analysis.router)
app.include_router(wallet_memory.router)
app.include_router(test_vectors.router)
app.include_router(metrics_router.router)
app.include_router(airdrop_router.router)
app.include_router(health_router.router)
app.include_router(hosting_router.router)
app.include_router(license_router.router)
app.include_router(retention_router.router)

# ── Team Access Middleware ──────────────────────────────────
# P0-3 fix: team keys are now persisted via KeyStore (not in-memory dict)
# and use role-based access control via require_role dependency.


@app.post(
    "/api/v1/team/keys",
    tags=["team-keys"],
    summary="Create Team Key",
    description="Create a team API key with specific role and permissions.",
)
async def create_team_key(label: str, role: str = "operator", request: Request = None):
    """Create a team API key with specific role and permissions.

    Roles (hierarchy: admin > operator > viewer):
      admin    — full access, can manage keys
      operator — generate wallets, view vault
      viewer   — read-only access

    Team keys are scoped to your user account. Audit log records which
    team member performed each action. Keys are persisted to disk via
    KeyStore (survive restarts).
    """
    # Only admins can create team keys (enforced via the request auth context)
    caller_key = getattr(request.state, "api_key_obj", None)
    if not caller_key or caller_key.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only admin role can create team keys",
        )

    if role not in ("admin", "operator", "viewer"):
        raise HTTPException(
            status_code=400,
            detail="Invalid role. Must be admin, operator, or viewer.",
        )
    store = get_key_store()
    key_id, raw_key = store.create(label=label, role=role, owner=caller_key.owner or caller_key.id)
    get_audit().log(
        "team.key.create",
        actor=caller_key.id,
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


@app.get(
    "/api/v1/team/keys",
    tags=["team-keys"],
    summary="List Team Keys",
    description="List all team API keys.",
)
async def list_team_keys(request: Request):
    """List all team API keys (admin only)."""
    caller_key = getattr(request.state, "api_key_obj", None)
    if not caller_key or caller_key.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    store = get_key_store()
    return {"keys": store.list()}


@app.delete(
    "/api/v1/team/keys/{key_id}",
    tags=["team-keys"],
    summary="Revoke Team Key",
    description="Revoke a team API key immediately.",
)
async def revoke_team_key(key_id: str, request: Request):
    """Revoke a team API key immediately (admin only)."""
    caller_key = getattr(request.state, "api_key_obj", None)
    if not caller_key or caller_key.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    store = get_key_store()
    revoked = store.revoke(key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail=f"Key {key_id} not found")
    get_audit().log("team.key.revoke", actor=caller_key.id, resource=key_id)
    return {"revoked": True, "key_id": key_id}


@app.get(
    "/health",
    summary="Health",
    description="Health check endpoint. Checks vault, key store, proof of generation, and webhook deliverer status.",
)
async def health():
    status = "ok"
    status_code = 200
    checks = {}

    try:
        from core.vault import get_vault

        v = get_vault()
        v.count()
        checks["vault"] = "ok"
    except Exception as e:
        checks["vault"] = f"error: {e}"
        status = "degraded"

    try:
        from core.auth import get_key_store

        ks = get_key_store()
        ks.list()
        checks["key_store"] = "ok"
    except Exception as e:
        checks["key_store"] = f"error: {e}"
        status = "degraded"

    try:
        from core.proof import get_proof

        p = get_proof()
        p.stats()
        checks["proof"] = "ok"
    except Exception as e:
        checks["proof"] = f"error: {e}"
        status = "degraded"

    try:
        from core.webhooks import get_webhook_deliverer

        wd = get_webhook_deliverer()
        checks["webhooks"] = "ok" if wd._running else "not_running"
    except Exception as e:
        checks["webhooks"] = f"error: {e}"
        status = "degraded"

    if status == "degraded":
        status_code = 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "version": cfg.version,
            "service": "walletpress",
            "checks": checks,
        },
    )


@app.get("/version", summary="Version", description="Service version endpoint.")
async def version():
    from core.config import cfg

    return {
        "version": cfg.version,
        "service": "WalletPress API",
        "title": cfg.title,
        "description": cfg.description,
        "status": "operational",
    }


@app.get(
    "/",
    summary="Root",
    description="API root endpoint. Returns service metadata, version, docs links, and trust/security information.",
)
async def root():
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


@app.get(
    "/trust/build",
    tags=["trust"],
    summary="Trust Build",
    description="Reproducible build verification. Returns source commit hash and Docker image metadata for build reproducibility verification.",
)
async def trust_build():
    """Reproducible build verification.

    Returns the current source commit hash and Docker image metadata.
    Anyone can rebuild from source and compare the Docker image SHA
    to verify the running code matches the open-source repository.
    """
    from core.proof import get_source_tree_hash

    commit = get_source_tree_hash()
    return {
        "service": "WalletPress",
        "source_repository": "https://github.com/cryptorugmuncher/walletpress",
        "source_commit": commit,
        "source_commit_url": f"https://github.com/cryptorugmuncher/walletpress/commit/{commit}"
        if commit != "unknown"
        else "",
        "build_method": "Docker multi-stage build (see Dockerfile)",
        "build_command": "docker build -t walletpress .",
        "verify_command": "docker pull walletpress && docker inspect walletpress --format '{{.Id}}' | cut -d: -f2",
        "reproducible": True,
        "note": "Build from source, compare the image SHA. If they match, the binary matches the code.",
    }


@app.get(
    "/trust/audit",
    tags=["trust"],
    summary="Trust Audit",
    description="Public audit log. Returns recent immutable audit entries proving operational transparency.",
)
async def trust_audit():
    """Public audit log — immutable, append-only.

    Returns recent audit entries. The audit log cannot be modified —
    only new entries can be appended. This proves operational transparency.
    """
    from core.audit import get_audit

    audit = get_audit()
    entries = audit.query(limit=50)
    stats = audit.stats()
    return {
        "service": "WalletPress Audit Log",
        "total_entries": stats.get("total_entries", 0),
        "file_size_bytes": stats.get("file_size", 0),
        "append_only": True,
        "immutable": True,
        "recent_entries": entries,
        "note": "Audit log is append-only. Entries cannot be modified or deleted.",
    }


# Mount AI Wallet Agent MCP server (SSE transport)
# Connect via: opencode, Claude Code, Cursor, or any MCP client
# Endpoint: GET /mcp/sse  or  POST /mcp/messages
# SECURITY: every /mcp route requires WP_ADMIN_KEY (require_admin_key_on_mcp).
# This mount MUST be registered before the root "/" x402 mount below — Starlette
# matches the first mount whose prefix matches, and Mount("/") matches every
# path, which would otherwise swallow /mcp/* and return 404.
app.mount("/mcp", agent_mcp.sse_app())

# Mount x402 marketplace as sub-app (was standalone x402_service.py)
# x402's endpoints (/api/v1/marketplace/generate, /api/v1/marketplace/pricing, etc.) become
# available at /api/v1/marketplace/... when mounted at root. Its /health is not mounted
# to avoid conflict with main app's /health.
app.mount("/", x402_app)


# ── WebSocket Event Stream ───────────────────────────────────
_ws_clients: dict[WebSocket, set[str]] = {}
_ws_rate: dict[WebSocket, float] = {}
_WS_RATE_LIMIT = 10  # messages per second per connection


@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    """WebSocket endpoint for real-time wallet events.

    Connect and receive push events as they happen:
      {"event": "wallet.generated", "data": {"wallet_id": "...", "chain": "eth"}}
      {"event": "payment.received", "data": {"tx_hash": "...", "amount": 100}}

    Subscribe to specific event types by sending a JSON message:
      {"subscribe": ["wallet.generated", "payment.received"]}
    Default: subscribe to all events.

    Rate limit: 10 messages/second per connection.

    Authentication (security-hardened):
      Priority 1: Sec-WebSocket-Protocol header (e.g. "wp-auth-<API_KEY>")
      Priority 2: First JSON message with {"token": "<API_KEY>"}
      [DEPRECATED] ?token= query parameter — logs warning, will be removed
      NEVER use URL query params for auth tokens — they leak to access logs.
    """
    import asyncio as _asyncio

    await ws.accept()

    # ── Extract token securely (never from URL query params) ──
    token = ""

    # Priority 1: Sec-WebSocket-Protocol header (does not appear in access logs)
    protocols = ws.headers.get("sec-websocket-protocol", "")
    for p in protocols.split(","):
        p = p.strip()
        if p.startswith("wp-auth-"):
            token = p[8:]
            break

    # Priority 2: First WebSocket message (within 5s timeout)
    if not token:
        try:
            auth_msg = await _asyncio.wait_for(ws.receive_json(), timeout=5.0)
            token = auth_msg.get("token", "")
            # If auth message also contains subscribe data, apply it immediately
            if token and "subscribe" in auth_msg:
                subs = auth_msg["subscribe"]
                if isinstance(subs, list) and all(isinstance(s, str) for s in subs):
                    _ws_clients[ws] = set(subs)
        except (_asyncio.TimeoutError, _asyncio.CancelledError):
            pass
        except Exception as e:
            logger.debug(f"WebSocket auth message error: {e}")

    # [DEPRECATED] Fallback: query parameter — leaks to logs
    if not token:
        query_token = ws.query_params.get("token", "")
        if query_token:
            logger.warning(
                "DEPRECATED: WebSocket ?token= query parameter used. "
                "This leaks tokens to access logs. Use Sec-WebSocket-Protocol header instead."
            )
            token = query_token

    # ── Verify token ──
    if token:
        from core.auth import get_key_store

        ks = get_key_store()
        if not ks.verify(token):
            await ws.send_json({"error": "Invalid API key"})
            await ws.close()
            return

    if ws not in _ws_clients:
        _ws_clients[ws] = set()
    _ws_rate[ws] = time.monotonic()

    try:
        while True:
            data = await ws.receive_text()
            now = time.monotonic()
            last = _ws_rate.get(ws, 0)
            if now - last < 1.0 / _WS_RATE_LIMIT:
                await ws.send_json(
                    {"event": "rate_limited", "data": {"message": "Slow down (max 10 msg/s)"}}
                )
                continue
            _ws_rate[ws] = now
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                if data == "ping":
                    await ws.send_json({"event": "pong"})
                continue
            if isinstance(msg, dict) and "subscribe" in msg:
                subs = msg["subscribe"]
                if isinstance(subs, list) and all(isinstance(s, str) for s in subs):
                    _ws_clients[ws] = set(subs)
                    await ws.send_json({"event": "subscribed", "data": {"events": subs}})
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.pop(ws, None)
        _ws_rate.pop(ws, None)


async def broadcast_ws(event_type: str, data: dict):
    """Broadcast an event to all connected WebSocket clients (respects subscriptions)."""
    message = json.dumps({"event": event_type, "data": data})
    dead: list[WebSocket] = []
    for ws, subs in list(_ws_clients.items()):
        if subs and event_type not in subs:
            continue
        try:
            await ws.send_text(message)
        except Exception as e:
            logger.debug(f"WebSocket send failed: {e}")
            dead.append(ws)
    for ws in dead:
        _ws_clients.pop(ws, None)
        _ws_rate.pop(ws, None)


# Wire event bus to WebSocket broadcast
from core.event_bus import subscribe as _subscribe_events


def _ws_event_forwarder(event_type: str, data: dict):
    """Forward events from the bus to the WebSocket broadcast loop."""
    import asyncio

    asyncio.get_event_loop().create_task(broadcast_ws(event_type, data))


_subscribe_events(_ws_event_forwarder)


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else cfg.port
    uvicorn.run("main:app", host=cfg.host, port=port, reload=True)
