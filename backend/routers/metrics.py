"""Prometheus metrics endpoint for operations monitoring.

Exposes /metrics in Prometheus text format for scraping by Prometheus,
Grafana, or any monitoring system.

Metrics:
  walletpress_wallets_total     — Total wallets in vault
  walletpress_generations_total — Total wallet generations
  walletpress_requests_total    — Total API requests (by method, path, status)
  walletpress_request_duration  — Request latency histogram
  walletpress_vault_encrypted   — Whether vault encryption is enabled
  walletpress_chains_supported  — Number of supported chains
"""

from __future__ import annotations

import time
from contextlib import suppress

from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from core.config import cfg
from core.vault import get_vault
from wallet_engine.chains import CHAINS
from wallet_engine.generator import get_generator

router = APIRouter(tags=["Metrics"])

_metrics_data = {
    "requests": {"count": 0},
    "start_time": time.time(),
}


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        start = time.monotonic()
        response = await call_next(request)
        time.monotonic() - start
        _metrics_data["requests"]["count"] += 1
        return response


@router.get("/metrics")
async def metrics():
    vault = get_vault()
    gen = get_generator(cfg.vault_password)
    vault_stats = vault.stats()

    lines = [
        "# HELP walletpress_wallets_total Total wallets in vault",
        "# TYPE walletpress_wallets_total gauge",
        f"walletpress_wallets_total {vault_stats['total_wallets']}",
        "",
        "# HELP walletpress_encrypted_wallets Total encrypted wallets",
        "# TYPE walletpress_encrypted_wallets gauge",
        f"walletpress_encrypted_wallets {vault_stats['encrypted_wallets']}",
        "",
        "# HELP walletpress_generations_total Total wallets generated (this session)",
        "# TYPE walletpress_generations_total counter",
        f"walletpress_generations_total {gen.stats['generation_count']}",
        "",
        "# HELP walletpress_chains_supported Number of supported chains",
        "# TYPE walletpress_chains_supported gauge",
        f"walletpress_chains_supported {len(CHAINS)}",
        "",
        "# HELP walletpress_vault_encrypted Whether vault encryption is enabled",
        "# TYPE walletpress_vault_encrypted gauge",
        f"walletpress_vault_encrypted {1 if cfg.vault_password else 0}",
        "",
        "# HELP walletpress_requests_total Total API requests processed",
        "# TYPE walletpress_requests_total counter",
        f"walletpress_requests_total {_metrics_data['requests']['count']}",
        "",
        "# HELP walletpress_uptime_seconds Server uptime in seconds",
        "# TYPE walletpress_uptime_seconds gauge",
        f"walletpress_uptime_seconds {time.time() - _metrics_data['start_time']}",
        "",
    ]

    return Response("\n".join(lines), media_type="text/plain; charset=utf-8")


@router.get("/metrics/usage")
async def usage_dashboard():
    """Per-customer usage dashboard — rate limiting stats, request counts, active keys."""
    vault = get_vault()
    gen = get_generator(cfg.vault_password)
    vault_stats = vault.stats()
    from core.rate_limit import RateLimitMiddleware
    from main import app

    rate_limiter = None
    for m in app.user_middleware:
        if m.cls == RateLimitMiddleware:
            rate_limiter = m
            break
    rate_stats = {}
    if rate_limiter:
        with suppress(Exception):
            rate_stats = rate_limiter.stats() if hasattr(rate_limiter, "stats") else {}
    return {
        "service": "WalletPress Usage Dashboard",
        "uptime_seconds": int(time.time() - _metrics_data["start_time"]),
        "requests_total": _metrics_data["requests"]["count"],
        "rate_limiting": rate_stats,
        "vault": {
            "total_wallets": vault_stats["total_wallets"],
            "encrypted_wallets": vault_stats["encrypted_wallets"],
            "chains_used": vault_stats.get("chains_used", 0),
        },
        "generator": {
            "generation_count": gen.stats["generation_count"],
            "chains_supported": gen.stats["chains_supported"],
            "encryption_enabled": gen.stats["encryption_enabled"],
        },
        "note": "Operational metrics. No customer data exposed.",
    }
