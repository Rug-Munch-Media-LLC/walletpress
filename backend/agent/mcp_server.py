"""WalletPress AI Agent MCP Server — All wallet operations as AI-callable tools.

Every tool is a @tool decorator. The MCP server can be:
- Run standalone via `uvicorn agent.mcp_server:mcp_app` or `python -m agent.mcp_server`
- Mounted as a FastAPI sub-app in main.py
- Connected to any MCP client (Claude Code, opencode, Cursor, etc.)

This module is a RE-EXPORT AGGREGATOR. The single shared FastMCP instance
and the HITL helpers live in `agent.mcp.instance`; the tools are grouped
into submodules:

- agent.mcp.safety      — safety & HITL tools
- agent.mcp.wallets     — wallet/vault tools (+ `_evm_sweep`)
- agent.mcp.chains      — chain / agent-intel tools
- agent.mcp.scheduling  — scheduler / anomaly tools
- agent.mcp.proof       — proof-of-generation / x402 tools

Every public name is re-exported here UNCHANGED because external importers
resolve against this module: `agent/orchestrator.py` uses
`importlib.import_module("agent.mcp_server")` + `getattr()` for the 16 plan
tools, `agent/scheduler.py` imports `_evm_sweep`, `main.py` and
`adapters/*` import `mcp`.
"""

from __future__ import annotations

from agent.mcp.chains import (
    agent_execute,
    agent_plan,
    chains_list,
    validate_address,
)
from agent.mcp.instance import (
    _HITL_SKIP_LOCAL,
    _confirmed_call,
    _is_hitl_skip,
    _safety_check,
    _set_hitl_skip,
    _write_with_hitl,
    logger,
    mcp,
)
from agent.mcp.proof import (
    marketplace_transparency,
    proof_attestations,
    proof_commit_pending,
    proof_provenance,
    proof_roots,
    proof_verify_wallet,
    verify_order,
)
from agent.mcp.safety import (
    address_allowlist,
    address_blocklist,
    address_check,
    address_list,
    agent_audit,
    agent_audit_verify,
    agent_confirm,
    agent_kill,
    agent_limits,
    agent_pending,
    agent_referral_status,
    agent_reject,
    agent_resurrect,
    agent_simulate,
)
from agent.mcp.scheduling import (
    anomaly_monitor,
    anomaly_scan,
    schedule_dca,
    schedule_list,
    schedule_remove,
)
from agent.mcp.wallets import (
    _evm_sweep,
    balance_check,
    vault_balances,
    vault_delete,
    vault_get,
    vault_list,
    vault_stats,
    wallet_from_mnemonic,
    wallet_generate,
    wallet_rotate,
    wallet_sweep,
)

__all__ = [
    "_HITL_SKIP_LOCAL",
    "_confirmed_call",
    "_evm_sweep",
    "_is_hitl_skip",
    "_safety_check",
    "_set_hitl_skip",
    "_write_with_hitl",
    "address_allowlist",
    "address_blocklist",
    "address_check",
    "address_list",
    "agent_audit",
    "agent_audit_verify",
    "agent_confirm",
    "agent_execute",
    "agent_kill",
    "agent_limits",
    "agent_pending",
    "agent_plan",
    "agent_referral_status",
    "agent_reject",
    "agent_resurrect",
    "agent_simulate",
    "anomaly_monitor",
    "anomaly_scan",
    "balance_check",
    "chains_list",
    "logger",
    "marketplace_transparency",
    "mcp",
    "proof_attestations",
    "proof_commit_pending",
    "proof_provenance",
    "proof_roots",
    "proof_verify_wallet",
    "schedule_dca",
    "schedule_list",
    "schedule_remove",
    "validate_address",
    "vault_balances",
    "vault_delete",
    "vault_get",
    "vault_list",
    "vault_stats",
    "verify_order",
    "wallet_from_mnemonic",
    "wallet_generate",
    "wallet_rotate",
    "wallet_sweep",
]


# ── STANDALONE ─────────────────────────────────────────────


if __name__ == "__main__":
    mcp.run()
