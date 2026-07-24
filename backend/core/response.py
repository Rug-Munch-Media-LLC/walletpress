"""Standardized API response shapes — RFC 7807 / RFC 9457 Problem Details.

Every error response now follows RFC 7807::

    Error: {
        "type": "/errors/bad_request",
        "title": "Bad Request",
        "status": 400,
        "detail": "Human-readable message",
        "instance": "/api/v1/endpoint",
        "request_id": "req_abc123",
        "timestamp": "2026-07-24T..."
    }

Success responses remain unchanged::

    Success: {"data": ..., "meta": {"request_id": "...", "timestamp": ...}}
"""

from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime
from typing import Any

from fastapi.responses import JSONResponse


_STATUS_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    402: "Payment Required",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}


def _default_title(status: int) -> str:
    return _STATUS_TITLES.get(status, "Error")


def _code_to_type(code: str) -> str:
    """Convert dot-notation error code to URI path, e.g. 'auth.invalid_token' → '/errors/auth/invalid_token'."""
    return f"/errors/{code.replace('.', '/')}"


def success(data, status_code: int = 200, meta: dict | None = None) -> JSONResponse:
    """Return a success response with data and metadata."""
    body: dict = {"data": data}
    if meta:
        body["meta"] = {**meta, "timestamp": time.time()}
    else:
        body["meta"] = {"timestamp": time.time()}
    return JSONResponse(content=body, status_code=status_code)


def error(
    code: str,
    message: str,
    status_code: int = 400,
    details: dict | None = None,
    request_id: str | None = None,
    instance: str | None = None,
) -> JSONResponse:
    """Return an RFC 7807 Problem Details error response.

    Args:
        code: Machine-readable error code (e.g. 'bad_request', 'auth.invalid_token').
        message: Human-readable explanation of the error.
        status_code: HTTP status code (default 400).
        details: Optional field-level error details.
        request_id: Correlation ID for tracing.
        instance: URI of the request that triggered the error.
    """
    body: dict[str, Any] = {
        "type": _code_to_type(code) if code != "internal_error" else "about:blank",
        "title": _default_title(status_code),
        "status": status_code,
        "detail": message,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if request_id:
        body["request_id"] = request_id
    else:
        body["request_id"] = f"req_{secrets.token_hex(8)}"
    if instance:
        body["instance"] = instance
    if details:
        body["errors"] = details
    if code:
        body["code"] = code

    return JSONResponse(content=body, status_code=status_code)


def created(data) -> JSONResponse:
    return success(data, status_code=201)


def no_content() -> JSONResponse:
    return JSONResponse(content=None, status_code=204)


def bad_request(message: str, details: dict | None = None, instance: str | None = None) -> JSONResponse:
    return error("bad_request", message, 400, details, instance=instance)


def unauthorized(message: str = "Authentication required", instance: str | None = None) -> JSONResponse:
    return error("unauthorized", message, 401, instance=instance)


def forbidden(message: str = "Access denied", instance: str | None = None) -> JSONResponse:
    return error("forbidden", message, 403, instance=instance)


def not_found(message: str = "Resource not found", instance: str | None = None) -> JSONResponse:
    return error("not_found", message, 404, instance=instance)


def conflict(message: str, details: dict | None = None, instance: str | None = None) -> JSONResponse:
    return error("conflict", message, 409, details, instance=instance)


def too_many_requests(message: str = "Rate limit exceeded", instance: str | None = None) -> JSONResponse:
    return error("too_many_requests", message, 429, instance=instance)


def server_error(message: str = "Internal server error", instance: str | None = None) -> JSONResponse:
    return error("server_error", message, 500, instance=instance)
