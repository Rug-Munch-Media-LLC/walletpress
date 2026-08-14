"""Safety & HITL tools for the WalletPress AI Agent.

Registration, confirmation, kill/resurrect, limits, simulation, referral
status, audit trail, and address book tools.

All tools register on the shared `mcp` instance from `agent.mcp.instance`
and use the shared HITL helpers (`_write_with_hitl`, `_confirmed_call`).
"""

from __future__ import annotations

from agent.mcp.instance import _confirmed_call, mcp
from core.agent_safety import (
    address_book_list,
    allowlist_add,
    audit_log,
    audit_trail,
    blocklist_add,
    check_address,
    confirm_action,
    get_actor,
    kill_agent as safety_kill,
    list_limits,
    list_pending,
    reject_action,
    resurrect_agent as safety_resurrect,
    simulate_transaction,
    verify_audit_chain,
)


@mcp.tool()
def agent_confirm(confirmation_id: str) -> dict:
    """Confirm a pending action and execute it.

    After reviewing a pending confirmation, call this to approve execution.
    Returns the result of the underlying action.

    Args:
        confirmation_id: The ID from a previous agent_execute or write request
    """
    # Bind the confirmation to the authenticated actor (admin key holder).
    # agent_safety.confirm_action() rejects confirmations whose requesting
    # actor differs, closing the self-approval bypass.
    actor = get_actor() or "human"
    result = confirm_action(confirmation_id, confirmed_by=actor)
    if "error" in result:
        return result
    action = result["action"]
    params = result["params"]

    # Execute the approved action inside HITL-skip mode
    from agent.mcp.scheduling import (
        anomaly_monitor,
        schedule_dca,
        schedule_remove,
    )
    from agent.mcp.wallets import (
        vault_delete,
        wallet_from_mnemonic,
        wallet_generate,
        wallet_rotate,
        wallet_sweep,
    )

    tool_map = {
        "wallet_generate": lambda: _confirmed_call(action, params, wallet_generate, **params),
        "wallet_from_mnemonic": lambda: _confirmed_call(
            action, params, wallet_from_mnemonic, **params
        ),
        "vault_delete": lambda: _confirmed_call(action, params, vault_delete, **params),
        "wallet_rotate": lambda: _confirmed_call(action, params, wallet_rotate, **params),
        "wallet_sweep": lambda: _confirmed_call(action, params, wallet_sweep, **params),
        "schedule_dca": lambda: _confirmed_call(action, params, schedule_dca, **params),
        "schedule_remove": lambda: _confirmed_call(action, params, schedule_remove, **params),
        "anomaly_monitor": lambda: _confirmed_call(action, params, anomaly_monitor, **params),
    }

    fn = tool_map.get(action)
    if not fn:
        return {"error": f"No confirmation handler for action: {action}"}

    audit_log(action, params, {"status": "executing"}, confirmed_by=actor)
    try:
        exec_result = fn()
        audit_log(action, params, exec_result, confirmed_by=actor)
        return {"confirmed": True, "action": action, "result": exec_result}
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        audit_log(action, params, {"error": err_msg}, confirmed_by=actor)
        return {"confirmed": True, "action": action, "error": err_msg}


@mcp.tool()
def agent_reject(confirmation_id: str, reason: str = "") -> dict:
    """Reject a pending action without executing it.

    Args:
        confirmation_id: The ID from a previous agent_execute or write request
        reason: Optional reason for rejection
    """
    result = reject_action(confirmation_id, reason)
    if "error" in result:
        return result
    audit_log("agent_reject", {"confirmation_id": confirmation_id}, result)
    return result


@mcp.tool()
def agent_pending() -> list[dict]:
    """List all pending confirmation requests waiting for your approval."""
    return list_pending()


@mcp.tool()
def agent_kill(reason: str = "") -> dict:
    """Emergency stop the agent immediately.

    All pending plans are canceled. Agent goes into read-only mode.
    Returns a resurrection key needed to re-enable the agent.

    Args:
        reason: Why are you killing the agent?
    """
    result = safety_kill(reason)
    audit_log("agent_kill", {"reason": reason}, result)
    return result


@mcp.tool()
def agent_resurrect(key: str) -> dict:
    """Re-enable a killed agent using the resurrection key.

    Args:
        key: The resurrection key from agent_kill()
    """
    result = safety_resurrect(key)
    if "error" not in result:
        audit_log("agent_resurrect", {}, result)
    return result


@mcp.tool()
def agent_limits() -> dict:
    """Show current spending limits and usage across all chains."""
    return list_limits()


@mcp.tool()
async def agent_simulate(chain: str, from_address: str, to_address: str, amount: float) -> dict:
    """Simulate a transaction to see gas costs and expected outcome before executing.

    Args:
        chain: Chain key (eth, sol, etc.)
        from_address: Source wallet address
        to_address: Destination address
        amount: Amount in native tokens
    """
    return await simulate_transaction(chain, from_address, to_address, amount)


@mcp.tool()
def agent_referral_status() -> dict:
    """Show the agent's revenue/referral configuration.

    In FREEMIUM mode, the agent uses Rug Munch Media's referral codes
    on every swap/trade — this costs you nothing and helps fund development.
    In SELF-REFERRAL mode, you keep 100% of referral revenue.

    P2-14: In multi-tenant (hosted) mode, this endpoint used to leak the
    operator's referral codes and wallets to any tenant. Now we redact
    sensitive fields (codes, wallet addresses) in hosted mode. The
    operator can see everything; tenants see only that the system is
    configured.

    Shows which platforms are configured, which need wallet setup,
    and what revenue share each platform provides.
    """
    import os

    from plugins.defi import (
        REF_AXIOM,
        REF_BANANA,
        REF_GMGN,
        REF_HYPERLIQUID_WALLET,
        REF_JUPITER_WALLET,
        REF_ODINBOT,
        REF_PADRE,
        REVENUE_MODE,
    )

    # Hosted mode = multi-tenant. Redact operator secrets from response.
    is_hosted = bool(os.getenv("WP_HOSTED_MODE", ""))
    redact_secrets = is_hosted and REVENUE_MODE == "freemium"

    def _maybe_redact(value, kind: str = "value") -> str:
        if redact_secrets:
            if kind == "wallet":
                return "[REDACTED — operator-controlled]"
            return "[REDACTED]"
        return value or "NOT SET"

    platforms = [
        {
            "platform": "Jupiter",
            "type": "fee_account",
            "share": "50bps",
            "configured": bool(REF_JUPITER_WALLET),
            "wallet": _maybe_redact(REF_JUPITER_WALLET, "wallet"),
            "docs": "https://jup.ag/referral",
        },
        {
            "platform": "Hyperliquid",
            "type": "builder_code",
            "share": "up to 0.1%/trade",
            "configured": bool(REF_HYPERLIQUID_WALLET),
            "wallet": _maybe_redact(REF_HYPERLIQUID_WALLET, "wallet"),
            "docs": "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes.md",
        },
        {
            "platform": "GMGN",
            "type": "code",
            "share": "40%",
            "configured": True,
            "code": _maybe_redact(REF_GMGN),
            "setup": "Use code at gmgn.ai",
        },
        {
            "platform": "OdinBot",
            "type": "code",
            "share": "40%",
            "configured": True,
            "code": _maybe_redact(REF_ODINBOT),
            "setup": "Use code at t.me/OdinBot",
        },
        {
            "platform": "Banana Gun",
            "type": "code",
            "share": "40%",
            "configured": True,
            "code": _maybe_redact(REF_BANANA),
            "setup": "Use code at t.me/BananaGunBot",
        },
        {
            "platform": "Axiom",
            "type": "code",
            "share": "30%",
            "configured": True,
            "code": _maybe_redact(REF_AXIOM),
            "setup": "Use code at t.me/AxiomTrade",
        },
        {
            "platform": "Padre",
            "type": "code",
            "share": "35%",
            "configured": True,
            "code": _maybe_redact(REF_PADRE),
            "setup": "Use code at t.me/PadreBot",
        },
    ]

    freemium_note = ""
    if REVENUE_MODE == "freemium":
        configured = sum(1 for p in platforms if p.get("configured"))
        unconfigured = sum(1 for p in platforms if not p.get("configured"))
        freemium_note = (
            f"{configured} platforms sending revenue, "
            f"{unconfigured} need wallet setup (Jupiter + Hyperliquid). "
            f"Set WP_REF_REVENUE_MODE=self to keep your own referral revenue."
        )

    return {
        "revenue_mode": REVENUE_MODE.upper(),
        "your_cost": "free (we cover referral fees)"
        if REVENUE_MODE == "freemium"
        else "you control your own codes",
        "platforms": platforms,
        "note": freemium_note,
        "secrets_redacted": redact_secrets,
        "how_to_configure": (
            "Jupiter: set WP_REF_JUPITER_WALLET (fee account). "
            "Hyperliquid: set WP_REF_HYPERLIQUID_WALLET (builder wallet, "
            "needs 100 USDC in perps)."
        ),
    }


@mcp.tool()
def agent_audit(limit: int = 50) -> list[dict]:
    """View the agent audit trail — every action logged with SHA-256 chain.

    Args:
        limit: Number of recent entries to show (default 50)
    """
    return audit_trail(limit)


@mcp.tool()
def agent_audit_verify() -> dict:
    """Verify the integrity of the entire audit trail.

    Recomputes all SHA-256 hashes and checks the chain is unbroken.
    """
    return verify_audit_chain()


@mcp.tool()
def address_allowlist(address: str, chain: str, label: str = "") -> dict:
    """Add an address to the agent's allowlist. The agent can only send to known addresses.

    Args:
        address: Wallet address to allow
        chain: Chain key (eth, sol, btc, etc.)
        label: Optional human-readable label (e.g. 'Exchange wallet')
    """
    return allowlist_add(address, chain, label)


@mcp.tool()
def address_blocklist(address: str, chain: str, label: str = "") -> dict:
    """Add an address to the blocklist. The agent will never send funds here.

    Args:
        address: Wallet address to block
        chain: Chain key
        label: Reason for blocking
    """
    return blocklist_add(address, chain, label)


@mcp.tool()
def address_list(list_type: str = "") -> list[dict]:
    """List addresses in the agent's address book.

    Args:
        list_type: 'allowlist', 'blocklist', or '' for all
    """
    return address_book_list(list_type)


@mcp.tool()
def address_check(address: str, chain: str) -> dict:
    """Check if an address is safe to send funds to.

    Checks against: user's blocklist, known scam database, and
    optionally the allowlist (if WP_AGENT_REQUIRE_ALLOWLIST=1).

    Args:
        address: Wallet address to check
        chain: Chain key
    """
    return check_address(address, chain)
