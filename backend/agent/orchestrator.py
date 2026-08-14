"""Agent Orchestrator — Natural language → multi-step wallet operation plans.

The orchestrator uses the configured AI provider to translate plain English
instructions into structured plans. Plans are then executed by the MCP tools.

This is the "brain" of the AI Wallet Agent. It handles:
- Parsing intent from natural language
- Decomposing complex ops into step-by-step tool calls
- Confirmation/approval workflow
- Error recovery and rollback
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent.providers import get_llm_client, get_provider

logger = logging.getLogger("wp.agent.orchestrator")

SYSTEM_PROMPT = """You are the WalletPress AI Wallet Agent. You help users manage their crypto wallets across 55 blockchains.

You have these tools available to execute wallet operations:
- wallet_generate(chain, label, count) — generate wallets
- wallet_from_mnemonic(mnemonic, chains) — derive from seed phrase
- vault_list(chain, limit) — list wallets
- vault_get(wallet_id) — get wallet details + private key
- vault_delete(wallet_id) — delete a wallet
- vault_stats() — vault statistics
- balance_check(chain, address) — check balance
- vault_balances(chain) — all wallet balances
- wallet_rotate(wallet_id, reason) — rotate keys
- wallet_sweep(from_wallet_id, to_address) — sweep funds
- chains_list() — list supported chains
- validate_address(chain, address) — validate address format
- schedule_dca(chain, amount, frequency, to_address, label) — set up DCA
- schedule_list() — list scheduled tasks
- anomaly_scan(address, chain) — scan for anomalies
- anomaly_monitor(wallet_id, webhook_url) — monitor wallet

Your task: Analyze the user's request and create a step-by-step plan.

Return ONLY valid JSON with this structure:
{
    "intent": "brief description of what the user wants",
    "steps": [
        {
            "tool": "tool_name",
            "args": {"arg1": "value1"},
            "description": "what this step does"
        }
    ],
    "warnings": ["any security concerns"],
    "needs_confirmation": true/false
}

Rules:
1. ALWAYS prefer existing wallets over generating new ones
2. Flag anything that involves moving funds for confirmation
3. If the request is ambiguous, ask clarifying questions in "warnings"
4. Keep private keys SAFE — never expose them unnecessarily
5. For "show me everything" queries, use vault_list + vault_balances"""


def _call_llm(system: str, user: str) -> str:
    """Call the configured LLM and return the response text."""
    provider = get_provider()
    client = get_llm_client(provider)
    model = provider.default_model
    logger.info(f"Planning via {provider.name} ({model})")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return json.dumps(
            {
                "intent": "failed to plan",
                "steps": [],
                "warnings": [
                    f"AI provider error: {e}. Check your WP_AI_PROVIDER and WP_AI_API_KEY configuration."
                ],
                "needs_confirmation": False,
                "error": str(e),
            }
        )


def plan_operation(prompt: str, context: str = "") -> dict:
    """Take natural language and return a structured operation plan."""
    user = prompt
    if context:
        user = f"Context:\n{context}\n\nRequest:\n{prompt}"
    raw = _call_llm(SYSTEM_PROMPT, user)

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        # LLM didn't return valid JSON — return as explanation
        return {
            "intent": "raw response",
            "steps": [],
            "explanation": raw,
            "warnings": ["Could not parse structured plan. Raw response shown above."],
            "needs_confirmation": False,
        }
    return plan


def execute_plan(plan: list[dict] | str, confirm: bool = False) -> dict:
    """Execute a plan by calling MCP tools sequentially.

    Args:
        plan: List of steps or JSON string
        confirm: If True, requires confirmation
    """
    import ast

    if isinstance(plan, str):
        try:
            plan_data = json.loads(plan)
        except (json.JSONDecodeError, TypeError):
            plan_data = (
                ast.literal_eval(plan)
                if isinstance(plan, str) and plan.strip().startswith("[")
                else {"steps": []}
            )
        plan = plan_data.get("steps", []) if isinstance(plan_data, dict) else plan_data

    if not plan:
        return {"error": "No steps in plan", "results": []}

    if confirm:
        return {
            "status": "awaiting_confirmation",
            "steps": [s.get("description", s.get("tool", "unknown")) for s in plan],
            "message": "Confirm execution via agent_execute(plan=<same_plan>, confirm=False)",
        }

    results = []
    for i, step in enumerate(plan):
        tool_name = step.get("tool", "")
        args = step.get("args", {})
        description = step.get("description", tool_name)
        logger.info(f"Step {i + 1}/{len(plan)}: {description}")
        try:
            result = _call_tool(tool_name, args)
            results.append({"step": i, "tool": tool_name, "result": result, "success": True})
        except Exception as e:
            logger.error(f"Step {i + 1} failed: {e}")
            results.append({"step": i, "tool": tool_name, "error": str(e), "success": False})
            return {
                "status": "failed",
                "completed": i,
                "total": len(plan),
                "results": results,
                "error": f"Step '{description}' failed: {e}",
            }

    return {"status": "completed", "total": len(plan), "results": results}


def _call_tool(tool_name: str, args: dict) -> Any:
    """Call an MCP tool function by name."""
    import importlib

    # Map tool names to their module functions
    tool_map = {
        "wallet_generate": ("agent.mcp_server", "wallet_generate"),
        "wallet_from_mnemonic": ("agent.mcp_server", "wallet_from_mnemonic"),
        "vault_list": ("agent.mcp_server", "vault_list"),
        "vault_get": ("agent.mcp_server", "vault_get"),
        "vault_delete": ("agent.mcp_server", "vault_delete"),
        "vault_stats": ("agent.mcp_server", "vault_stats"),
        "balance_check": ("agent.mcp_server", "balance_check"),
        "vault_balances": ("agent.mcp_server", "vault_balances"),
        "wallet_rotate": ("agent.mcp_server", "wallet_rotate"),
        "wallet_sweep": ("agent.mcp_server", "wallet_sweep"),
        "chains_list": ("agent.mcp_server", "chains_list"),
        "validate_address": ("agent.mcp_server", "validate_address"),
        "schedule_dca": ("agent.mcp_server", "schedule_dca"),
        "schedule_list": ("agent.mcp_server", "schedule_list"),
        "anomaly_scan": ("agent.mcp_server", "anomaly_scan"),
        "anomaly_monitor": ("agent.mcp_server", "anomaly_monitor"),
    }

    mod_path, fn_name = tool_map.get(tool_name, (None, None))
    if not mod_path:
        raise ValueError(f"Unknown tool: {tool_name}")

    mod = importlib.import_module(mod_path)
    fn = getattr(mod, fn_name)
    return fn(**args)
