"""Chain & agent-intel tools for the WalletPress AI Agent.

Address validation, chain registry listing, and the orchestrator-driven
planning/execution tools (`agent_plan`, `agent_execute`).
"""

from __future__ import annotations

from agent.mcp.instance import mcp

# ── CROSS-CHAIN ────────────────────────────────────────────


@mcp.tool()
def validate_address(chain: str, address: str) -> dict:
    """Validate if an address is structurally valid for a given chain.

    Args:
        chain: Chain key
        address: Address to validate
    """
    from wallet_engine.chains import CHAINS, validate_address as va

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
