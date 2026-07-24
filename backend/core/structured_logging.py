"""WalletPress — Structured JSON logging with structlog.

Per RMI AUTH_STANDARD.md, all services should use structlog with JSON
output in production for machine-parseable logs.

This module ensures BOTH structlog loggers AND stdlib logging.getLogger()
output structured JSON, so existing code using ``logger.info(...)``
continues to work while new code can use structlog's richer API.

Usage:
    from core.structured_logging import get_logger, setup_logging

    setup_logging(level="INFO")
    logger = get_logger("wp.service_name")
    logger.info("wallet_generated", chain="solana", count=5)

    # OR continue using stdlib logging.getLogger() — it will also
    # produce JSON output via the ProcessorFormatter handler.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

SERVICE_NAME = "walletpress"
_LOG_LEVEL_ENV = "WP_LOG_LEVEL"
_DEFAULT_LEVEL = "INFO"


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger for a module."""
    return structlog.get_logger(name)


def setup_logging(level: str | None = None) -> None:
    """Configure structlog with JSON output for production.

    Call once at process startup. If *level* is None, reads from
    ``WP_LOG_LEVEL`` env var (default: INFO).

    Installs a ProcessorFormatter on the root handler so that stdlib
    ``logging.getLogger()`` calls also emit JSON.
    """
    if level is None:
        level = os.getenv(_LOG_LEVEL_ENV, _DEFAULT_LEVEL).upper()

    is_prod = level == "INFO"

    # ── Build structlog processor chain ──────────────────────────
    shared_processors: list[Any] = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if is_prod:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ── Configure root logger with ProcessorFormatter ────────────
    # This makes stdlib logging.getLogger() output structured JSON too.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                *shared_processors,
                renderer,
            ],
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # Remove default handlers
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level, logging.INFO))

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "botocore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
