"""RFC 7807 problem-details responses for the x402 marketplace service.

One job: turn an exception into a machine-readable problem document, and wire
that into a FastAPI app. Response bodies are never built by the endpoints.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

TITLES = {
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


def problem(
    request: Request,
    status: int,
    detail: str,
    *,
    type_uri: str = "about:blank",
) -> JSONResponse:
    """Build an RFC 7807 response document."""
    return JSONResponse(
        status_code=status,
        content={
            "type": type_uri,
            "title": TITLES.get(status, "Error"),
            "status": status,
            "detail": detail,
            "request_id": getattr(request.state, "request_id", "-"),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


async def http_exception_handler(
    request: Request, exc: HTTPException | StarletteHTTPException
) -> JSONResponse:
    """Render an HTTP error as a problem document."""
    status = exc.status_code
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    type_uri = "/errors/not_found" if status == 404 else "about:blank"
    return problem(request, status, detail, type_uri=type_uri)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: never leak an internal error message to a client."""
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        return await http_exception_handler(request, exc)

    logging.getLogger("x402").exception(
        "unhandled_exception request_id=%s path=%s",
        getattr(request.state, "request_id", "-"),
        request.url.path,
    )
    return problem(request, 500, "Internal server error")


def install_error_handlers(app: FastAPI) -> None:
    """Attach the RFC 7807 handlers to an app."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
