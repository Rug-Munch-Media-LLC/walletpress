"""Rate Limiting Middleware — token bucket per IP with X-RateLimit headers.

Protects against abuse. Each IP gets a configurable number of requests
per minute. Excess requests return 429 Too Many Requests with RFC 7807
error format and standard X-RateLimit-* headers.

Trust: Rate limiting protects YOUR server resources. No telemetry,
no tracking, no data collection.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request
    from starlette.responses import Response


class TokenBucket:
    def __init__(self, rate: int, per_seconds: int = 60):
        self.rate = rate
        self.per_seconds = per_seconds
        self.tokens: float = rate
        self.last_refill: float = time.monotonic()

    def consume(self) -> tuple[bool, float, float]:
        """Try to consume a token.

        Returns:
            Tuple of (allowed, remaining_tokens, seconds_until_full).
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.rate, self.tokens + elapsed * (self.rate / self.per_seconds))
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            allowed = True
        else:
            allowed = False
        remaining = max(0.0, self.tokens)
        seconds_until_full = (
            math.ceil((self.rate - remaining) / (self.rate / max(1, self.per_seconds)))
            if not allowed
            else 0
        )
        return allowed, remaining, seconds_until_full


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiter per IP address AND per API key.

    Health endpoints are exempt from rate limiting.
    Configure with WP_RATE_LIMIT env var (requests per minute).

    API keys get their own buckets (per-key rate limiting for hosted users).
    Emits X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset headers.
    """

    def __init__(self, app, rate: int = 60, per_seconds: int = 60):
        super().__init__(app)
        self.rate = rate
        self.per_seconds = per_seconds
        self._buckets: dict[str, TokenBucket] = {}

    def _get_key(self, request: Request) -> str:
        """Get rate limiting key — API key if present, otherwise IP."""
        api_key = request.headers.get("X-API-Key", "") or request.headers.get(
            "Authorization", ""
        ).replace("Bearer ", "")
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

        allowed, remaining, reset_in = bucket.consume()

        if not allowed:
            retry_after = max(1, int(reset_in))
            return JSONResponse(
                status_code=429,
                content={
                    "type": "/errors/too_many_requests",
                    "title": "Too Many Requests",
                    "status": 429,
                    "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "request_id": getattr(request.state, "request_id", ""),
                    "code": "too_many_requests",
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.rate),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + reset_in)),
                },
            )

        response = await call_next(request)

        # Inject rate limit headers on every response
        response.headers["X-RateLimit-Limit"] = str(self.rate)
        response.headers["X-RateLimit-Remaining"] = str(max(0, int(remaining)))
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + reset_in))
        return response

    def stats(self) -> dict:
        """Get rate limiting statistics — total buckets, active keys."""
        now = time.monotonic()
        active = 0
        for _, bucket in self._buckets.items():
            if now - bucket.last_refill < 300:
                active += 1
        return {
            "total_buckets": len(self._buckets),
            "active_in_last_5min": active,
            "rate_per_minute": self.rate,
        }
