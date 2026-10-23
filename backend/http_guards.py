"""Content-type guard for write endpoints.

POST/PUT/PATCH/DELETE must use application/json (multipart uploads exempt).
This blocks content-type smuggling and bypass of JSON body validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request

WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
CONTENT_TYPE_EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/metrics", "/mcp/", "/ws/")


async def enforce_json_content_type(request: Request, call_next):
    """Reject non-JSON Content-Type on write endpoints."""
    guarded = request.method in WRITE_METHODS and not request.url.path.startswith(
        CONTENT_TYPE_EXEMPT_PREFIXES
    )
    if guarded:
        content_type = (request.headers.get("content-type") or "").lower().strip()
        allowed = ("application/json", "multipart/form-data")
        if content_type and not content_type.startswith(allowed):
            return JSONResponse(
                status_code=415,
                content={
                    "detail": "Unsupported media type. Use Content-Type: application/json.",
                    "code": "unsupported_media_type",
                },
            )
    return await call_next(request)
