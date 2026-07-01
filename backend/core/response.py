"""Standardized API response shapes.

Every response follows::

    Success: {"data": ..., "meta": {"request_id": "..."}}
    Error:   {"error": {"code": "...", "message": "...", "details": ...}}

This module provides helpers that all routers should use instead of
returning raw dicts. Migration is incremental — old endpoints that
return bare dicts still work via FastAPI's auto-serialisation.
"""

from __future__ import annotations

import time
import secrets

from fastapi.responses import JSONResponse


def success(data, status_code: int = 200, meta: dict | None = None) -> JSONResponse:
    body: dict = {"data": data}
    if meta:
        body["meta"] = {**meta, "timestamp": time.time()}
    else:
        body["meta"] = {"timestamp": time.time()}
    return JSONResponse(content=body, status_code=status_code)


def error(code: str, message: str, status_code: int = 400, details: dict | None = None, request_id: str | None = None) -> JSONResponse:
    body: dict = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details:
        body["error"]["details"] = details
    body["meta"] = {"request_id": request_id or f"req_{secrets.token_hex(8)}", "timestamp": time.time()}
    return JSONResponse(content=body, status_code=status_code)


def created(data) -> JSONResponse:
    return success(data, status_code=201)


def no_content() -> JSONResponse:
    return JSONResponse(content=None, status_code=204)


def bad_request(message: str, details: dict | None = None) -> JSONResponse:
    return error("bad_request", message, 400, details)


def unauthorized(message: str = "Authentication required") -> JSONResponse:
    return error("unauthorized", message, 401)


def forbidden(message: str = "Access denied") -> JSONResponse:
    return error("forbidden", message, 403)


def not_found(message: str = "Resource not found") -> JSONResponse:
    return error("not_found", message, 404)


def conflict(message: str, details: dict | None = None) -> JSONResponse:
    return error("conflict", message, 409, details)


def too_many_requests(message: str = "Rate limit exceeded") -> JSONResponse:
    return error("too_many_requests", message, 429)


def server_error(message: str = "Internal server error") -> JSONResponse:
    return error("server_error", message, 500)
