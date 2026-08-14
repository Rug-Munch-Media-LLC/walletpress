"""Shared FastMCP instance and HITL helpers for the WalletPress AI Agent tools.

Every tool submodule registers its `@mcp.tool()` decorators on the single
`mcp` instance defined here, so the `agent.mcp_server` aggregator exposes
every tool on one server.

The HITL (human-in-the-loop) machinery lives here because it is shared by
the safety, wallets, and scheduling tool submodules:

- `_write_with_hitl` — run safety checks and request confirmation for a WRITE action
- `_confirmed_call`  — execute a tool inside a confirmed flow (per-thread skip flag)
- `_safety_check`    — legacy lightweight WRITE gate (kept for back-compat)
"""

from __future__ import annotations

import logging
import threading

from mcp.server.fastmcp import FastMCP

from core.agent_safety import (
    audit_log,
    check_action_allowed,
    is_killed,
    request_confirmation,
)

logger = logging.getLogger("wp.agent.mcp")

mcp = FastMCP("WalletPress AI Agent", log_level="WARNING")


def _safety_check(action: str, params: dict) -> dict | None:
    """Run safety checks for a WRITE action. Returns error dict or None if OK."""
    # Kill switch
    if is_killed():
        return {"error": "Agent is emergency stopped. Use agent_resurrect() to re-enable."}

    # Permission tier
    allowed, reason = check_action_allowed(action)
    if not allowed:
        return {"error": reason}

    # All checks passed
    return None


_HITL_SKIP_LOCAL = threading.local()


def _is_hitl_skip() -> bool:
    return getattr(_HITL_SKIP_LOCAL, "skip", False)


def _set_hitl_skip(val: bool) -> None:
    _HITL_SKIP_LOCAL.skip = val


def _write_with_hitl(action: str, params: dict, reason: str = "") -> dict | None:
    """Run safety checks for a WRITE action.

    Returns:
        None if checks pass and the action should proceed directly.
        dict with error or confirmation request if action is blocked or needs HITL.
    """
    if _is_hitl_skip():
        return None  # Called from agent_confirm — skip safety, execute directly

    # Kill switch
    if is_killed():
        return {"error": "Agent is emergency stopped. Use agent_resurrect() to re-enable."}

    # Permission tier
    allowed, reason_tier = check_action_allowed(action)
    if not allowed:
        return {"error": reason_tier}

    # Request HITL confirmation (always for WRITE actions)
    result = request_confirmation(action, params, reason)
    audit_log(action, params, {"status": "pending_confirmation"}, confirmed_by="")
    return {
        "status": "pending_confirmation",
        "confirmation_id": result["confirmation_id"],
        "action": action,
        "reason": reason,
        "expires_at": result["expires_at"],
        "confirm_command": f"Use agent_confirm('{result['confirmation_id']}') to approve",
        "reject_command": f"Use agent_reject('{result['confirmation_id']}') to reject",
    }


def _confirmed_call(action: str, params: dict, fn, *args, **kwargs):
    """Execute a tool function inside a confirmed HITL flow.

    Sets the per-thread skip flag so the tool runs without requesting
    confirmation again. Thread-safe under concurrent requests.
    """
    _set_hitl_skip(True)
    try:
        return fn(*args, **kwargs)
    finally:
        _set_hitl_skip(False)
