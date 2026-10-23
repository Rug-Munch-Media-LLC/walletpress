"""Request correlation and access logging.

`RequestIDMiddleware` must be registered first: Starlette wraps middleware in
reverse registration order, so the first one added is the outermost and stamps
the request id before any other middleware, handler or log line runs.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger("wp")


class RequestIDMiddleware:
    """Generates X-Request-ID, stamps it on request.state and response headers."""

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


def get_request_id(request: Request) -> str:
    """Return the id stamped by RequestIDMiddleware ("-" when absent)."""
    return getattr(request.state, "request_id", "-")


async def log_requests(request: Request, call_next):
    """Log method, path, status and duration for every HTTP request."""
    start = time.time()
    request_id = get_request_id(request)
    response = await call_next(request)
    elapsed = time.time() - start
    logger.info(
        "http_request method=%s path=%s status=%d elapsed=%.3fs request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
        request_id,
    )
    return response
