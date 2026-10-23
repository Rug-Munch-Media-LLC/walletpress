"""WalletPress Backend — application assembly.

Usage:
    pip install -r requirements.txt
    uvicorn main:app --port 8010

    python main.py [port]      # via the walletpress CLI
    docker compose up          # containerised

Layout: routers/ hold the HTTP surface, main.py only assembles the app.
Middleware order lives in middleware_install.py; startup wiring in lifespan.py;
error envelopes in error_handlers.py; the event stream in ws_events.py.

Trust: fully open source. Private keys are encrypted at rest with
AES-256-GCM + Argon2id. The vault password is never logged.
"""

from __future__ import annotations

import logging
import os
import sys

from fastapi import FastAPI

from agent.mcp_server import mcp as agent_mcp
from core.config import cfg
from core.structured_logging import setup_logging
from error_handlers import register_exception_handlers
from lifespan import lifespan
from middleware_install import install_middleware
from routers import (
    airdrop as airdrop_router,
    chain_vault,
    health_monitor as health_router,
    hosting as hosting_router,
    license_router,
    metrics as metrics_router,
    retention as retention_router,
    test_vectors,
    wallet_admin,
    wallet_analysis,
    wallet_memory,
)
from system_routes import router as system_router
from team_keys_routes import router as team_keys_router
from trust_routes import router as trust_router
from ws_events import router as ws_router
from x402_service import app as x402_app

setup_logging(os.getenv("WP_LOG_LEVEL", "INFO"))

app = FastAPI(
    title=cfg.title,
    version=cfg.version,
    description=cfg.description,
    lifespan=lifespan,
)

install_middleware(app)
register_exception_handlers(app)

for _router in (
    chain_vault.router,
    wallet_admin.router,
    wallet_analysis.router,
    wallet_memory.router,
    test_vectors.router,
    metrics_router.router,
    airdrop_router.router,
    health_router.router,
    hosting_router.router,
    license_router.router,
    retention_router.router,
    team_keys_router,
    system_router,
    trust_router,
):
    app.include_router(_router)

# /mcp MUST be mounted before the root mount: Starlette matches the first mount
# whose prefix matches, and Mount("/") would otherwise swallow /mcp/* and 404.
app.mount("/mcp", agent_mcp.sse_app())

# x402 marketplace: its routes become /api/v1/marketplace/* under the root mount.
app.mount("/", x402_app)

# Registered last so the "/" mount above cannot shadow /ws/events.
app.include_router(ws_router)


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else cfg.port
    uvicorn.run("main:app", host=cfg.host, port=port, reload=True)
