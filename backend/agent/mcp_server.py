"""WalletPress AI Agent MCP Server — All wallet operations as AI-callable tools.

Every tool is a @tool decorator. The MCP server can be:
- Run standalone via `uvicorn agent.mcp_server:mcp_app` or `python -m agent.mcp_server`
- Mounted as a FastAPI sub-app in main.py
- Connected to any MCP client (Claude Code, opencode, Cursor, etc.)
"""

from __future__ import annotations

import logging
import time

from mcp.server.fastmcp import FastMCP

from core.config import cfg
from core.vault import WalletEntry, get_vault
from core.agent_safety import (
    check_action_allowed,
    is_killed,
    request_confirmation,
    confirm_action,
    reject_action,
    list_pending,
    check_address,
    check_spending_limit,
    record_spending,
    audit_log,
    simulate_transaction,
    kill_agent as safety_kill,
    resurrect_agent as safety_resurrect,
    allowlist_add,
    blocklist_add,
    address_book_list,
    list_limits,
    audit_trail,
    verify_audit_chain,
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


import threading

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


# ── SAFETY & HITL TOOLS ──────────────────────────────────


@mcp.tool()
def agent_confirm(confirmation_id: str) -> dict:
    """Confirm a pending action and execute it.

    After reviewing a pending confirmation, call this to approve execution.
    Returns the result of the underlying action.

    Args:
        confirmation_id: The ID from a previous agent_execute or write request
    """
    result = confirm_action(confirmation_id)
    if "error" in result:
        return result
    action = result["action"]
    params = result["params"]

    # Execute the approved action inside HITL-skip mode
    from agent.mcp_server import wallet_generate, wallet_from_mnemonic, vault_delete
    from agent.mcp_server import wallet_rotate, wallet_sweep
    from agent.mcp_server import schedule_dca, schedule_remove, anomaly_monitor

    TOOL_MAP = {
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

    fn = TOOL_MAP.get(action)
    if not fn:
        return {"error": f"No confirmation handler for action: {action}"}

    audit_log(action, params, {"status": "executing"}, confirmed_by="human")
    try:
        exec_result = fn()
        audit_log(action, params, exec_result, confirmed_by="human")
        return {"confirmed": True, "action": action, "result": exec_result}
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        audit_log(action, params, {"error": err_msg}, confirmed_by="human")
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
    from plugins.defi import REVENUE_MODE, REF_JUPITER_WALLET, REF_HYPERLIQUID_WALLET
    from plugins.defi import REF_GMGN, REF_ODINBOT, REF_BANANA, REF_AXIOM, REF_PADRE

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


# ── WALLET GENERATION ──────────────────────────────────────


@mcp.tool()
def wallet_generate(chain: str, label: str = "", count: int = 1) -> dict:
    """Generate one or more wallets for any supported chain.

    Args:
        chain: Chain key (eth, sol, btc, trx, bsc, polygon, base, ...)
        label: Optional human-readable label
        count: Number of wallets to generate (default 1, max 100)
    """
    hitl = _write_with_hitl(
        "wallet_generate",
        {"chain": chain, "label": label, "count": count},
        f"Generate {count} wallet(s) on {chain}",
    )
    if "confirmation_id" in hitl:
        return hitl
    from wallet_engine.generator import get_generator

    vault = get_vault()
    generator = get_generator(cfg.vault_password)
    wallets = []
    created_ids = []
    try:
        for i in range(count):
            lbl = label or f"{chain}_{i + 1}_{int(time.time())}"
            try:
                wallet = generator.generate(chain, label=lbl)
            except ValueError as e:
                # P2-3: roll back any partial inserts so caller doesn't see
                # inconsistent state (e.g. 5 of 10 wallets persisted, error
                # in the middle, caller doesn't know which were saved).
                for wid in created_ids:
                    vault.delete(wid)
                return {"error": str(e), "rolled_back": created_ids}
            entry = WalletEntry(
                id=f"wp_agent_{chain}_{int(time.time() * 1000)}_{i}",
                chain=wallet.chain,
                address=wallet.address,
                label=wallet.label,
                tags=wallet.tags,
                created_at=wallet.created_at,
                encrypted_key=wallet.private_key_hex if wallet.encrypted else "",
                public_key=wallet.public_key_hex,
                derivation_path=wallet.derivation_path,
                encrypted=wallet.encrypted,
            )
            vault.put(entry)
            created_ids.append(entry.id)
            wallets.append(
                {
                    "id": entry.id,
                    "chain": entry.chain,
                    "address": entry.address,
                    "label": entry.label,
                }
            )
    except Exception as e:
        # Any unexpected error — roll back partial inserts.
        for wid in created_ids:
            vault.delete(wid)
        return {"error": f"{type(e).__name__}: {e}", "rolled_back": created_ids}
    return {"generated": len(wallets), "wallets": wallets}


@mcp.tool()
def wallet_from_mnemonic(mnemonic: str, chains: list[str] | None = None) -> dict:
    """Derive wallets from a BIP39 mnemonic phrase.

    Args:
        mnemonic: BIP39 seed phrase (12 or 24 words)
        chains: List of chains to derive (empty = all 55 chains)
    """
    hitl = _write_with_hitl(
        "wallet_from_mnemonic", {"chains": chains}, "Derive wallets from a mnemonic phrase"
    )
    if hitl:
        return hitl
    from wallet_engine.chains import CHAINS
    from wallet_engine.generator import get_generator

    vault = get_vault()
    generator = get_generator(cfg.vault_password)
    chain_list = chains or list(CHAINS.keys())
    results = {}
    for ck in chain_list:
        try:
            wallet = generator.generate(ck, mnemonic=mnemonic, label=f"mnemonic_{ck}")
        except ValueError:
            results[ck] = {"error": "chain not supported"}
            continue
        entry = WalletEntry(
            id=f"wp_mcp_mnemonic_{ck}_{int(time.time())}",
            chain=wallet.chain,
            address=wallet.address,
            label=wallet.label,
            tags=wallet.tags + ["from_mnemonic"],
            created_at=wallet.created_at,
            encrypted_key=wallet.private_key_hex if wallet.encrypted else "",
            public_key=wallet.public_key_hex,
            derivation_path=wallet.derivation_path,
            encrypted=wallet.encrypted,
        )
        vault.put(entry)
        results[ck] = {"address": entry.address, "wallet_id": entry.id}
    return {"derived_for": len(results), "chains": results}


# ── VAULT MANAGEMENT ───────────────────────────────────────


@mcp.tool()
def vault_list(chain: str = "", limit: int = 50) -> list[dict]:
    """List wallets in the vault (no private keys returned).

    Args:
        chain: Optional filter by chain
        limit: Max results (default 50)
    """
    vault = get_vault()
    wallets = vault.list(chain=chain, limit=limit) if chain else vault.list(limit=limit)
    return [{
        "id": w.id, "chain": w.chain, "address": w.address,
        "label": w.label, "tags": w.tags, "created_at": w.created_at,
        "encrypted": w.encrypted, "balance_usd": w.balance_usd,
    } for w in wallets]


@mcp.tool()
def vault_get(wallet_id: str, include_private_key: bool = False) -> dict:
    """Get wallet details from the vault.

    By default returns only public info (address, public_key, derivation_path).
    Private key export requires explicit opt-in via include_private_key=True
    AND goes through HITL confirmation. This is the LAST line of defense
    before a plaintext key leaves the process — never bypass it.

    P2-4 fix: Previously the function unconditionally decrypted and returned
    the private key, with no audit trail of the export beyond the agent
    audit (which the caller controls). Now:
      - Default: returns public info only (no private key field at all)
      - include_private_key=True: requires HITL confirmation
      - Every export logged via audit_log with explicit 'key_export' tag

    Args:
        wallet_id: Wallet ID from vault_list
        include_private_key: Set True to export the decrypted private key
    """
    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        return {"error": f"Wallet {wallet_id} not found"}

    result = {
        "id": wallet.id,
        "chain": wallet.chain,
        "address": wallet.address,
        "label": wallet.label,
        "tags": wallet.tags,
        "created_at": wallet.created_at,
        "public_key": wallet.public_key,
        "derivation_path": wallet.derivation_path,
        "encrypted": wallet.encrypted,
        "balance_usd": wallet.balance_usd,
        "private_key_exported": False,
    }

    if not include_private_key:
        return result

    # Private key export requires HITL confirmation. This is a destructive
    # operation — the caller is about to receive a plaintext key.
    hitl = _write_with_hitl(
        "key_export",
        {"wallet_id": wallet_id, "chain": wallet.chain, "address": wallet.address},
        f"Export private key for {wallet.chain} wallet {wallet.address[:12]}...",
    )
    if "confirmation_id" in hitl:
        return hitl

    if wallet.encrypted_key and wallet.encrypted and cfg.vault_password:
        from wallet_engine.generator import get_generator

        generator = get_generator(cfg.vault_password)
        result["private_key"] = generator.decrypt_key(wallet.encrypted_key)
        result["private_key_exported"] = True
        audit_log(
            "key_export",
            {"wallet_id": wallet_id, "chain": wallet.chain, "address": wallet.address},
            {"status": "exported"},
            confirmed_by="human",
        )
        logger.warning(
            f"Private key exported for wallet {wallet_id} ({wallet.chain}, {wallet.address[:12]}...)"
        )
    elif wallet.encrypted_key:
        # Encrypted but we have no KEK. Return encrypted form, not the raw key.
        result["private_key_encrypted"] = wallet.encrypted_key
        result["note"] = (
            "Wallet is encrypted but vault password is not set in this "
            "process. Cannot decrypt. Set WP_VAULT_PASSWORD or configure the "
            "file-based KEK."
        )
    return result


@mcp.tool()
def vault_delete(wallet_id: str) -> dict:
    """Delete a wallet permanently.

    Args:
        wallet_id: Wallet ID to delete
    """
    hitl = _write_with_hitl("vault_delete", {"wallet_id": wallet_id},
                            f"Permanently delete wallet {wallet_id}")
    if hitl:
        return hitl
    vault = get_vault()
    if vault.delete(wallet_id):
        return {"deleted": True, "wallet_id": wallet_id}
    return {"error": f"Wallet {wallet_id} not found"}


@mcp.tool()
def vault_stats() -> dict:
    """Get vault statistics — total wallets, encrypted count, chains used, rotations."""
    vault = get_vault()
    return vault.stats()


# ── BALANCE & ANALYSIS ─────────────────────────────────────


@mcp.tool()
async def balance_check(chain: str, address: str) -> dict:
    """Check wallet balance on any supported chain.

    Args:
        chain: Chain key (eth, sol, btc, trx, ...)
        address: Wallet address
    """
    from routers.balance_fetcher import fetch_balance

    return await fetch_balance(chain, address)


@mcp.tool()
def vault_balances(chain: str = "") -> dict:
    """Get balances for all wallets in the vault.

    Args:
        chain: Optional chain filter
    """
    vault = get_vault()
    wallets = vault.list(chain=chain, limit=500) if chain else vault.list(limit=500)
    return {
        "wallets": [
            {"id": w.id, "chain": w.chain, "address": w.address, "balance_usd": w.balance_usd}
            for w in wallets
        ],
        "total_usd": sum(w.balance_usd for w in wallets),
        "wallet_count": len(wallets),
    }


# ── WALLET MANAGEMENT ──────────────────────────────────────


@mcp.tool()
def wallet_rotate(wallet_id: str, reason: str = "agent_rotation") -> dict:
    """Rotate a wallet to a new address. Old wallet preserved with 'rotated' tag.

    Args:
        wallet_id: ID of existing wallet
        reason: Rotation reason
    """
    hitl = _write_with_hitl(
        "wallet_rotate",
        {"wallet_id": wallet_id, "reason": reason},
        f"Rotate keys for wallet {wallet_id}: {reason}",
    )
    if hitl:
        return hitl
    from wallet_engine.generator import get_generator

    vault = get_vault()
    old = vault.get(wallet_id)
    if not old:
        return {"error": f"Wallet {wallet_id} not found"}
    generator = get_generator(cfg.vault_password)
    new = generator.generate(
        old.chain, label=f"rotation_{old.chain}_{int(time.time())}", tags=["rotated", "active"]
    )
    new_entry = WalletEntry(
        id=f"wp_rot_{old.chain}_{int(time.time())}",
        chain=new.chain,
        address=new.address,
        label=new.label,
        tags=new.tags,
        created_at=new.created_at,
        encrypted_key=new.private_key_hex if new.encrypted else "",
        public_key=new.public_key_hex,
        derivation_path=new.derivation_path,
        encrypted=new.encrypted,
    )
    vault.put(new_entry)
    vault.record_rotation(old.id, new.address, reason=reason)
    return {
        "rotated": True,
        "old_wallet_id": old.id,
        "old_address": old.address,
        "new_wallet_id": new_entry.id,
        "new_address": new_entry.address,
        "chain": old.chain,
    }


@mcp.tool()
def wallet_sweep(from_wallet_id: str, to_address: str) -> dict:
    """Sweep ALL funds from a vault wallet to an external address.

    Implements actual on-chain transfer for EVM chains (Ethereum, Base,
    Polygon, Arbitrum, Optimism, BNB Chain, Avalanche, Fantom, Gnosis, etc.).
    For non-EVM chains (Solana, TRON, BTC family), returns a clear
    "not implemented" error with the transaction params the caller can sign.

    Security checks performed BEFORE signing:
      1. Address allow/block list (block known scam addresses)
      2. Spending limits (per-chain, per-period)
      3. HITL confirmation (human must approve via agent_confirm)

    Args:
        from_wallet_id: Source wallet ID from vault
        to_address: Destination address (must be valid for the chain)
    """
    from core.balance_fetcher import EVM_RPC

    # Address safety check
    vault = get_vault()
    wallet = vault.get(from_wallet_id)
    chain = wallet.chain if wallet else "unknown"
    addr_check = check_address(to_address, chain)
    if not addr_check["allowed"]:
        return {"error": f"Address blocked: {addr_check['reason']}"}

    # Spending limit check
    limit_check = check_spending_limit(chain, 0)
    if not limit_check["allowed"]:
        return {"error": f"Spending limit exceeded: {limit_check['exceeded']}"}

    hitl = _write_with_hitl(
        "wallet_sweep",
        {"from_wallet_id": from_wallet_id, "to_address": to_address},
        f"Sweep funds from {from_wallet_id} to {to_address}",
    )
    if hitl:
        return hitl

    wallet = vault.get(from_wallet_id)
    if not wallet:
        return {"error": f"Wallet {from_wallet_id} not found"}

    # EVM chain: build, sign, and broadcast via tx_broadcaster
    if chain in EVM_RPC:
        return _evm_sweep(wallet, to_address, chain)

    # Non-EVM: return intent + clear "not implemented" notice
    return {
        "status": "intent_only",
        "chain": chain,
        "wallet_id": from_wallet_id,
        "from_address": wallet.address,
        "to_address": to_address,
        "note": (
            f"Auto-broadcast not yet implemented for {chain}. "
            f"Sign the transaction externally with the wallet's private key "
            f"and broadcast via tx_broadcaster.broadcast()."
        ),
    }


def _evm_sweep(wallet, to_address: str, chain: str) -> dict:
    """Build, sign, and broadcast an EVM sweep transaction.

    Returns the tx_hash on success or an error dict on failure.
    """
    import asyncio
    from eth_account import Account
    from web3 import Web3
    from web3.exceptions import Web3Exception

    from core.balance_fetcher import EVM_RPC
    from routers.tx_broadcaster import _evm_broadcast

    rpc_url = EVM_RPC.get(chain)
    if not rpc_url:
        return {"error": f"No RPC configured for chain {chain}"}

    # Decrypt the private key from the vault
    from wallet_engine.generator import get_generator

    gen = get_generator(cfg.vault_password)
    if not wallet.encrypted_key or not wallet.encrypted:
        return {"error": f"Wallet {wallet.id} has no encrypted key (client-side only?)"}
    try:
        privkey_hex = gen.decrypt_key(wallet.encrypted_key)
    except Exception as e:
        return {"error": f"Failed to decrypt private key: {e}"}

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
        if not w3.is_connected():
            return {"error": f"Cannot connect to RPC for {chain}"}

        account = Account.from_key(privkey_hex)
        nonce = w3.eth.get_transaction_count(account.address)
        gas_price = w3.eth.gas_price
        chain_id = w3.eth.chain_id

        # Get balance — sweep = balance - gas
        balance_wei = w3.eth.get_balance(account.address)
        # Estimate gas for a simple transfer (21k) + buffer
        gas_limit = 21000
        gas_cost_wei = gas_limit * gas_price
        if balance_wei <= gas_cost_wei:
            return {
                "error": "Insufficient balance to cover gas",
                "balance_wei": balance_wei,
                "gas_cost_wei": gas_cost_wei,
            }

        value_wei = balance_wei - gas_cost_wei

        # Build the transaction
        tx = {
            "nonce": nonce,
            "to": to_address,
            "value": value_wei,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": chain_id,
        }

        # Sign
        signed = account.sign_transaction(tx)

        # Broadcast via existing tx_broadcaster helper (handles errors uniformly)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_evm_broadcast(chain, signed.raw_transaction.hex()))
        finally:
            loop.close()

        if result.get("broadcast"):
            # Record the spending
            try:
                amount_eth = float(w3.from_wei(value_wei, "ether"))
                record_spending(chain, amount_eth)
            except Exception:
                pass
            audit_log(
                "wallet_sweep",
                {"from_wallet_id": wallet.id, "to_address": to_address, "chain": chain},
                {"tx_hash": result["tx_hash"], "amount_wei": value_wei},
                confirmed_by="human",
            )
            return {
                "status": "broadcast",
                "chain": chain,
                "from_wallet_id": wallet.id,
                "from_address": wallet.address,
                "to_address": to_address,
                "tx_hash": result["tx_hash"],
                "amount_wei": value_wei,
                "amount_native": float(w3.from_wei(value_wei, "ether")),
                "gas_cost_wei": gas_cost_wei,
                "explorer_url": f"https://etherscan.io/tx/{result['tx_hash']}"
                if chain == "eth"
                else None,
            }
        else:
            return {
                "error": f"Broadcast failed: {result.get('error', 'unknown')}",
                "chain": chain,
            }
    except Web3Exception as e:
        return {"error": f"Web3 error: {e}", "chain": chain}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "chain": chain}


# ── CROSS-CHAIN ────────────────────────────────────────────


@mcp.tool()
def validate_address(chain: str, address: str) -> dict:
    """Validate if an address is structurally valid for a given chain.

    Args:
        chain: Chain key
        address: Address to validate
    """
    from wallet_engine.chains import validate_address as va, CHAINS

    chain_info = CHAINS.get(chain.lower())
    if not chain_info:
        return {"error": f"Unsupported chain: {chain}"}
    valid = va(chain, address)
    return {
        "chain": chain,
        "address": address,
        "valid": valid,
        "expected_pattern": chain_info.address_pattern,
    }


@mcp.tool()
def chains_list() -> dict:
    """List all 55 supported blockchains with metadata."""
    from wallet_engine.chains import CHAINS

    families = set()
    chain_list = []
    for k, c in sorted(CHAINS.items()):
        families.add(c.family.value)
        chain_list.append(
            {
                "key": k,
                "name": c.name,
                "symbol": c.symbol,
                "family": c.family.value,
                "curve": c.curve,
            }
        )
    return {
        "total_chains": len(chain_list),
        "total_families": len(families),
        "chains": chain_list,
    }


# ── AGENT INTELLIGENCE ─────────────────────────────────────


@mcp.tool()
def agent_plan(prompt: str, context: str = "") -> dict:
    """Plan a multi-step wallet operation from natural language.

    The LLM analyzes the prompt and returns a structured plan of tool calls
    to execute. Use this for complex operations like:
    - "sweep all ETH from my vault to 0x..."
    - "generate 5 SOL wallets for my airdrop campaign"
    - "rotate my oldest wallet and check the new balance"
    - "tell me my total portfolio value across all chains"

    Args:
        prompt: Natural language instruction
        context: Optional context (e.g. current vault state summary)
    """
    from agent.orchestrator import plan_operation

    return plan_operation(prompt, context)


@mcp.tool()
def agent_execute(plan: list[dict] | str, confirm: bool = False) -> dict:
    """Execute a pre-approved multi-step plan.

    Args:
        plan: The plan from agent_plan, or a JSON string of steps
        confirm: If True, requires human confirmation before executing
    """
    from agent.orchestrator import execute_plan

    return execute_plan(plan, confirm=confirm)


# ── SCHEDULER ──────────────────────────────────────────────


@mcp.tool()
def schedule_dca(
    chain: str, amount: float, frequency: str = "weekly", to_address: str = "", label: str = ""
) -> dict:
    """Set up a DCA (dollar-cost averaging) schedule.

    Generates a wallet and periodically sends funds to it.

    Args:
        chain: Chain key
        amount: Amount in native token per interval
        frequency: 'daily', 'weekly', 'biweekly', 'monthly'
        to_address: Optional destination (empty = generate new wallet each time)
        label: Optional label for generated wallets
    """
    hitl = _write_with_hitl(
        "schedule_dca",
        {"chain": chain, "amount": amount, "frequency": frequency},
        f"Set up {frequency} DCA of {amount} {chain}",
    )
    if hitl:
        return hitl
    from agent.scheduler import add_dca_task

    return add_dca_task(chain, amount, frequency, to_address, label)


@mcp.tool()
def schedule_list() -> list[dict]:
    """List all active scheduled tasks (DCA, sweeps, monitors)."""
    from agent.scheduler import scheduler

    return scheduler.list_tasks()


@mcp.tool()
def schedule_remove(task_id: str) -> dict:
    """Remove a scheduled task.

    Args:
        task_id: ID from schedule_list
    """
    hitl = _write_with_hitl(
        "schedule_remove", {"task_id": task_id}, f"Remove scheduled task {task_id}"
    )
    if hitl:
        return hitl
    from agent.scheduler import scheduler

    if scheduler.remove_task(task_id):
        return {"removed": True, "task_id": task_id}
    return {"error": f"Task {task_id} not found"}


# ── ANOMALY DETECTION ──────────────────────────────────────


@mcp.tool()
async def anomaly_scan(address: str, chain: str = "eth") -> dict:
    """Scan a wallet for anomalous activity.

    Checks: unusually large transactions, new address interactions,
    rapid-fire transactions, unusual timing.

    Args:
        address: Wallet address to scan
        chain: Chain key
    """
    from agent.detector import scan_wallet

    return await scan_wallet(address, chain)


@mcp.tool()
def anomaly_monitor(wallet_id: str, webhook_url: str = "") -> dict:
    """Set up continuous monitoring for a wallet.

    Triggers alerts on: large transfers, first-time interactions,
    unusual volume spikes, rapid consecutive transactions.

    Args:
        wallet_id: Wallet ID from vault
        webhook_url: Optional webhook for alerts
    """
    from agent.scheduler import add_monitor_task

    return add_monitor_task(wallet_id, webhook_url)


# ── PROOF OF GENERATION ────────────────────────────────────


@mcp.tool()
def proof_attestations() -> dict:
    """Get Proof of Generation statistics — total attestations, committed, uncommitted roots."""
    from core.proof import get_proof

    return get_proof().stats()


@mcp.tool()
def proof_commit_pending(chain: str = "local") -> dict:
    """Commit all pending attestations to a Merkle root.

    Args:
        chain: 'local' (SQLite, free), 'arweave' (permanent, ~$0.000001),
               'ethereum' (on-chain, ~$5-50 gas)
    """
    from core.proof import get_proof

    proof = get_proof()
    root_hash, count = proof.compute_merkle_root()
    if not root_hash:
        return {"committed": False, "reason": "No pending attestations"}
    result = proof.commit(root_hash, count, commitment_chain=chain)
    return {
        "committed": True,
        "root_hash": root_hash,
        "attestation_count": count,
        "chain": chain,
        "commitment_tx": result.get("commitment_tx", ""),
        "verification_url": result.get("verification_url", ""),
    }


@mcp.tool()
def proof_verify_wallet(wallet_id: str) -> dict:
    """Verify a wallet's Proof of Generation attestation.

    Args:
        wallet_id: Wallet ID from vault_list
    """
    from core.proof import get_proof
    from core.vault import get_vault

    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        return {"error": f"Wallet {wallet_id} not found"}
    result = get_proof().verify(wallet_id, wallet.address, wallet.public_key)
    return result


@mcp.tool()
def proof_provenance(wallet_id: str) -> dict:
    """Get the complete cryptographic provenance for a wallet.

    Includes the Merkle proof path so it can be independently verified.
    This is the wallet's birth certificate.

    Args:
        wallet_id: Wallet ID from vault_list
    """
    from core.proof import get_proof
    from core.vault import get_vault

    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        return {"error": f"Wallet {wallet_id} not found"}
    result = get_proof().get_proof_by_wallet(wallet_id)
    return result


@mcp.tool()
def proof_roots(limit: int = 10) -> dict:
    """List recent Merkle roots committed for wallet attestations.

    Args:
        limit: Max roots to return (default 10)
    """
    from core.proof import get_proof

    proof = get_proof()
    return {
        "stats": proof.stats(),
        "roots": proof.get_roots(limit),
    }


@mcp.tool()
def verify_order(order_id: str) -> dict:
    """Verify an x402 marketplace order — proves we generated the wallets and didn't keep keys.

    Returns the order details, receipt signature, and attestation proof.
    Anyone can independently verify this order was fulfilled by WalletPress.

    Args:
        order_id: Order ID from the generate response (e.g. 'x402_abc123...')
    """
    from core.wallet_db_pool import DbPool
    from core.config import cfg
    from core.proof import get_receipt_public_key

    pool = DbPool(cfg.data_dir / "marketplace.db")
    row = pool.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if not row:
        return {"error": f"Order {order_id} not found"}
    pubkey = get_receipt_public_key()
    return {
        "order_id": order_id,
        "chain": row["chain"],
        "count": row["count"],
        "amount_usd": row["amount_usd"],
        "created_at": row["created_at"],
        "status": row["status"],
        "payment_method": "onchain"
        if row.get("payment_tx") and row["payment_tx"] != "free"
        else "free",
        "receipt_public_key": pubkey,
        "verification": {
            "keys_stored": False,
            "keys_returned_once": True,
            "open_source": "https://github.com/cryptorugmuncher/walletpress",
            "note": "This order was fulfilled by WalletPress. Keys were generated in memory and returned once.",
        },
    }


@mcp.tool()
def marketplace_transparency() -> dict:
    """Get the public transparency dashboard — stats, roots, guarantees.

    Proves WalletPress is operating transparently. No secrets here.
    """
    from core.proof import get_proof, get_receipt_public_key

    proof = get_proof()
    pstats = proof.stats()
    roots = proof.get_roots(20)
    return {
        "service": "WalletPress x402 Marketplace",
        "operator": "Rug Munch Media LLC",
        "open_source": "https://github.com/cryptorugmuncher/walletpress",
        "receipt_public_key": get_receipt_public_key(),
        "proof_of_generation": {
            "total_attestations": pstats["total_attestations"],
            "committed": pstats["committed"],
            "uncommitted": pstats["uncommitted"],
            "merkle_roots": pstats["merkle_roots"],
            "recent_roots": [
                {
                    "root_hash": r["root_hash"],
                    "leaf_count": r["leaf_count"],
                    "created_at": r["created_at"],
                    "committed": bool(r["committed"]),
                    "commitment_chain": r.get("commitment_chain", ""),
                    "commitment_tx": r.get("commitment_tx", ""),
                }
                for r in roots
            ],
        },
        "trust_guarantees": [
            "Keys generated in memory, returned once, never stored",
            "Every order signed with Ed25519 receipt",
            "Every wallet attested in SHA-256 Merkle tree",
            "Merkle roots committed to Arweave for permanent proof",
            "Open source — verify every line of code",
            "Reproducible Docker builds — image hash matches source",
            "No telemetry, no tracking, no data collection",
            "Audit trail append-only, immutable",
        ],
    }


# ── STANDALONE ─────────────────────────────────────────────


if __name__ == "__main__":
    mcp.run()
