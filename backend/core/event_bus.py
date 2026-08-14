"""Shared event bus — decouples producers from WebSocket broadcast.

Modules like x402_marketplace emit events here. main.py's WebSocket
broadcast loop reads from this bus. No circular imports.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("wp.event_bus")

_subscribers: list[Callable[[str, dict], None]] = []


def subscribe(fn: Callable[[str, dict], None]) -> None:
    """Register a callback for all events."""
    _subscribers.append(fn)


def emit(event_type: str, data: dict) -> None:
    """Emit an event to all subscribers (fire-and-forget)."""
    for fn in _subscribers:
        try:
            fn(event_type, data)
        except Exception as e:
            logger.debug(f"Event subscriber error: {e}")
