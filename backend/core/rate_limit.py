"""Rate Limiting Middleware — token bucket per IP.

Protects against abuse. Each IP gets a configurable number of requests
per minute. Excess requests return 429 Too Many Requests.

Trust: Rate limiting protects YOUR server resources. No telemetry,
no tracking, no data collection.
"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response



class TokenBucket:
    def __init__(self, rate: int, per_seconds: int = 60):
        self.rate = rate
        self.per_seconds = per_seconds
        self.tokens: float = rate
        self.last_refill: float = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.rate, self.tokens + elapsed * (self.rate / self.per_seconds))
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiter per IP address AND per API key.

    Health endpoints are exempt from rate limiting.
    Configure with WP_RATE_LIMIT env var (requests per minute).

    API keys get their own buckets (per-key rate limiting for hosted users).
    """

    def __init__(self, app, rate: int = 60, per_seconds: int = 60):
        super().__init__(app)
        self.rate = rate
        self.per_seconds = per_seconds
        self._buckets: dict[str, TokenBucket] = {}

    def _get_key(self, request: Request) -> str:
        """Get rate limiting key — API key if present, otherwise IP."""
        api_key = request.headers.get("X-API-Key", "") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if api_key:
            return f"key:{api_key[:16]}"
        return f"ip:{request.client.host if request.client else 'unknown'}"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self.rate <= 0:
            return await call_next(request)

        exempt_paths = ("/health", "/healthz", "/docs", "/openapi.json", "/metrics")
        if request.url.path.startswith(exempt_paths):
            return await call_next(request)

        key = self._get_key(request)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self.rate, self.per_seconds)
            self._buckets[key] = bucket

        if not bucket.consume():
            retry_after = int(self.per_seconds / self.rate)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)

    def stats(self) -> dict:
        """Get rate limiting statistics — total buckets, active keys."""
        now = time.monotonic()
        active = 0
        for key, bucket in self._buckets.items():
            if now - bucket.last_refill < 300:
                active += 1
        return {
            "total_buckets": len(self._buckets),
            "active_in_last_5min": active,
            "rate_per_minute": self.rate,
        }
