"""Agent Scheduler — Recurring wallet tasks.

Runs in the background alongside the main app. Handles:
- Dollar-cost averaging: generate wallet + schedule funding
- Periodic balance checks with anomaly alerts
- Scheduled rotation (rotate wallet every N days)
- Monitoring triggers (large tx alerts)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("wp.agent.scheduler")

TASKS_FILE = Path(os.getenv("WP_DATA_DIR", "/data")) / "agent_tasks.json"


@dataclass
class ScheduledTask:
    id: str
    type: str  # dca, sweep, monitor, rotate
    chain: str
    params: dict[str, Any] = field(default_factory=dict)
    interval_seconds: int = 604800  # default: weekly
    last_run: float = 0.0
    next_run: float = 0.0
    created_at: float = 0.0
    enabled: bool = True
    label: str = ""


class AgentScheduler:
    """Lightweight background scheduler for agent tasks.

    Uses a background thread that checks for due tasks every 60 seconds.
    Tasks are persisted to JSON for durability across restarts.
    """

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._load()

    def _path(self) -> Path:
        p = Path(os.getenv("WP_DATA_DIR", "/data"))
        p.mkdir(parents=True, exist_ok=True)
        return p / "agent_tasks.json"

    def _load(self):
        path = self._path()
        if path.exists():
            try:
                data = json.loads(path.read_text())
                for k, v in data.items():
                    self._tasks[k] = ScheduledTask(**v)
                logger.info(f"Loaded {len(self._tasks)} scheduled tasks")
            except Exception as e:
                logger.error(f"Failed to load tasks: {e}")

    def _save(self):
        path = self._path()
        try:
            path.write_text(json.dumps({k: v.__dict__ for k, v in self._tasks.items()}, indent=2, default=str))
        except Exception as e:
            logger.error(f"Failed to save tasks: {e}")

    def add_task(self, task: ScheduledTask) -> str:
        with self._lock:
            self._tasks[task.id] = task
            self._save()
        logger.info(f"Scheduled task added: {task.id} ({task.type}/{task.chain})")
        return task.id

    def remove_task(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                self._save()
                return True
        return False

    def list_tasks(self) -> list[dict]:
        with self._lock:
            return [{
                "id": t.id, "type": t.type, "chain": t.chain,
                "label": t.label, "interval_seconds": t.interval_seconds,
                "last_run": t.last_run, "next_run": t.next_run,
                "enabled": t.enabled,
            } for t in self._tasks.values()]

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="agent-scheduler")
        self._thread.start()
        logger.info("Agent scheduler started")

    def stop(self):
        self._running = False

    def _run_loop(self):
        while self._running:
            now = time.time()
            due: list[ScheduledTask] = []
            with self._lock:
                for t in self._tasks.values():
                    if t.enabled and t.next_run > 0 and now >= t.next_run:
                        due.append(t)
            for task in due:
                try:
                    self._execute_task(task)
                    task.last_run = now
                    task.next_run = now + task.interval_seconds
                    self._save()
                except Exception as e:
                    logger.error(f"Task {task.id} failed: {e}")
            time.sleep(60)

    def _execute_task(self, task: ScheduledTask):
        if task.type == "dca":
            self._exec_dca(task)
        elif task.type == "monitor":
            self._exec_monitor(task)
        elif task.type == "rotate":
            self._exec_rotate(task)

    def _exec_dca(self, task: ScheduledTask):
        """Execute a DCA task. If to_address is set, this is a REAL on-chain transfer
        (not just intent). For EVM chains, uses wallet_sweep-like logic to broadcast.
        For non-EVM, falls back to generating a destination wallet (legacy behavior).
        """
        from core.config import cfg
        from core.vault import WalletEntry, get_vault
        from wallet_engine.generator import get_generator
        vault = get_vault()
        generator = get_generator(cfg.vault_password)
        to_addr = task.params.get("to_address", "")
        from_wallet_id = task.params.get("from_wallet_id", "")
        label = task.label or f"dca_{task.chain}_{int(time.time())}"

        # If both from_wallet_id and to_addr are set, this is a real DCA transfer.
        # For EVM chains, broadcast via tx_broadcaster. For others, generate the
        # destination wallet and rely on the user to fund it externally.
        if from_wallet_id and to_addr:
            from_wallet = vault.get(from_wallet_id)
            if not from_wallet:
                logger.warning(f"DCA: from_wallet {from_wallet_id} not found")
                return
            if from_wallet.chain != task.chain:
                logger.warning(
                    f"DCA: wallet chain {from_wallet.chain} != task chain {task.chain}"
                )
                return
            # For EVM: actually broadcast the transfer
            from core.balance_fetcher import EVM_RPC
            if task.chain in EVM_RPC:
                # Lazy-import to avoid circular deps
                from agent.mcp_server import _evm_sweep
                result = _evm_sweep(from_wallet, to_addr, task.chain)
                if result.get("status") == "broadcast":
                    logger.info(
                        f"DCA: Broadcast {task.amount} {task.chain} → {to_addr} "
                        f"tx={result.get('tx_hash')}"
                    )
                else:
                    logger.error(f"DCA: Broadcast failed: {result.get('error')}")
                return
            # Non-EVM: just log the intent (no native broadcast implementation yet)
            logger.info(
                f"DCA: Intent {task.amount} {task.chain} → {to_addr} "
                f"(non-EVM: not auto-broadcast, external signing required)"
            )
            return

        # Legacy behavior: generate a destination wallet and let the user fund it
        if to_addr:
            logger.info(f"DCA: {task.amount} {task.chain} → {to_addr} (intent only)")
        else:
            wallet = generator.generate(task.chain, label=label, tags=["dca"])
            entry = WalletEntry(
                id=f"wp_dca_{task.chain}_{int(time.time())}",
                chain=wallet.chain, address=wallet.address, label=wallet.label,
                tags=wallet.tags, created_at=wallet.created_at,
                encrypted_key=wallet.private_key_hex if wallet.encrypted else "",
                encrypted=wallet.encrypted,
            )
            vault.put(entry)
            logger.info(f"DCA: Generated new {task.chain} wallet → {wallet.address}")

    def _exec_monitor(self, task: ScheduledTask):
        addr = task.params.get("address", "")
        chain = task.chain
        if addr:
            import asyncio

            from agent.detector import scan_wallet
            result = asyncio.run(scan_wallet(addr, chain))
            if result.get("anomalies"):
                logger.warning(f"Anomaly detected for {addr}: {result['anomalies']}")
                webhook = task.params.get("webhook_url", "")
                if webhook:
                    import httpx
                    try:
                        httpx.post(webhook, json={"event": "anomaly", "address": addr, "result": result}, timeout=10)
                    except Exception as e:
                        logger.error(f"Webhook failed: {e}")

    def _exec_rotate(self, task: ScheduledTask):
        from core.config import cfg
        from core.vault import WalletEntry, get_vault
        from wallet_engine.generator import get_generator
        vault = get_vault()
        wallet_id = task.params.get("wallet_id", "")
        if not wallet_id:
            return
        old = vault.get(wallet_id)
        if not old:
            logger.warning(f"Rotate task: wallet {wallet_id} not found")
            return
        generator = get_generator(cfg.vault_password)
        new = generator.generate(old.chain, label=f"scheduled_rotate_{int(time.time())}", tags=["rotated"])
        entry = WalletEntry(
            id=f"wp_sched_rot_{int(time.time())}",
            chain=new.chain, address=new.address, label=new.label,
            tags=new.tags, created_at=new.created_at,
            encrypted_key=new.private_key_hex if new.encrypted else "",
            encrypted=new.encrypted,
        )
        vault.put(entry)
        vault.record_rotation(old.id, new.address, reason="scheduled_rotation")
        logger.info(f"Scheduled rotation: {old.id} → {new.address}")


scheduler = AgentScheduler()


def add_dca_task(chain: str, amount: float, frequency: str = "weekly",
                 to_address: str = "", label: str = "") -> dict:
    import secrets
    freq_map = {"daily": 86400, "weekly": 604800, "biweekly": 1209600, "monthly": 2592000}
    interval = freq_map.get(frequency, 604800)
    now = time.time()
    task = ScheduledTask(
        id=f"dca_{secrets.token_hex(4)}",
        type="dca",
        chain=chain,
        params={"amount": amount, "to_address": to_address},
        interval_seconds=interval,
        next_run=now + interval,
        created_at=now,
        label=label or f"DCA {amount} {chain} {frequency}",
    )
    scheduler.add_task(task)
    return {
        "task_id": task.id,
        "type": "dca",
        "chain": chain,
        "amount": amount,
        "frequency": frequency,
        "next_run": task.next_run,
        "label": task.label,
    }


def add_monitor_task(wallet_id: str, webhook_url: str = "") -> dict:
    import secrets

    from core.vault import get_vault
    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        return {"error": f"Wallet {wallet_id} not found"}
    now = time.time()
    task = ScheduledTask(
        id=f"mon_{secrets.token_hex(4)}",
        type="monitor",
        chain=wallet.chain,
        params={"address": wallet.address, "wallet_id": wallet_id, "webhook_url": webhook_url},
        interval_seconds=3600,
        next_run=now + 3600,
        created_at=now,
        label=f"Monitor {wallet.address[:12]}...",
    )
    scheduler.add_task(task)
    return {
        "task_id": task.id,
        "type": "monitor",
        "chain": wallet.chain,
        "address": wallet.address,
        "interval": "hourly",
        "next_run": task.next_run,
    }
