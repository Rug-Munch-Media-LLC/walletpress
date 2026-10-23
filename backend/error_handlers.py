"""Exception handlers returning a consistent RFC 7807-style envelope.

Every error carries a request_id so a client report can be correlated with the
server log line without exposing internals (500s never leak the exception).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from request_context import get_request_id

logger = logging.getLogger("wp")

_TITLES = {
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
}


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Render an HTTPException as the standard error envelope."""
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    status = exc.status_code
    return JSONResponse(
        status_code=status,
        content={
            "type": "about:blank",
            "title": _TITLES.get(status, "Error"),
            "status": status,
            "detail": detail,
            "request_id": get_request_id(request),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the exception, return a generic 500 to the caller."""
    if isinstance(exc, (HTTPException, FastAPIHTTPException, StarletteHTTPException)):
        return await http_exception_handler(request, exc)
    logger.error(
        "unhandled_exception method=%s path=%s exc=%s request_id=%s",
        request.method,
        request.url.path,
        f"{type(exc).__name__}: {exc}",
        get_request_id(request),
    )
    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "Internal server error",
            "request_id": get_request_id(request),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers (all three HTTPException aliases resolve to one)."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(FastAPIHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
