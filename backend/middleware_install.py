"""Canonical middleware installation.

Registration order is load-bearing and mirrors the pre-split main.py exactly:
RequestIDMiddleware first (outermost), CORS, optional rate limit, metrics,
then the HTTP guards and the auth/licence layers, then access logging.
Changing the order changes which middleware sees a request first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.cors import CORSMiddleware

from auth_middleware import require_admin_key_on_mcp, require_auth_on_mutations
from core.config import cfg
from core.ip_allowlist import IPAllowlistMiddleware
from core.jwt_auth import JWTValidationMiddleware
from core.license_check import LicenseMiddleware
from core.rate_limit import RateLimitMiddleware
from http_guards import enforce_json_content_type
from request_context import RequestIDMiddleware, log_requests
from routers import metrics as metrics_router

if TYPE_CHECKING:
    from fastapi import FastAPI


def install_middleware(app: FastAPI) -> None:
    """Register every middleware in the canonical order."""
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

    app.middleware("http")(enforce_json_content_type)
    app.add_middleware(JWTValidationMiddleware)
    app.add_middleware(IPAllowlistMiddleware)
    app.add_middleware(LicenseMiddleware)
    app.middleware("http")(require_auth_on_mutations)
    app.middleware("http")(require_admin_key_on_mcp)
    app.middleware("http")(log_requests)
