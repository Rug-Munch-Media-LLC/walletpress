"""Scheduler & anomaly tools for the WalletPress AI Agent.

DCA scheduling, task listing/removal, and wallet anomaly scanning/monitoring.

These wrap the infra in `agent.scheduler` (background task runner) and
`agent.detector` (anomaly scanning). Named `scheduling` to avoid confusion
with `agent.scheduler`.
"""

from __future__ import annotations

from agent.mcp.instance import _write_with_hitl, mcp

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
