"""Immutable audit trail — append-only JSONL. Never modified, never deleted.

Trust principle: Every wallet operation is logged. The log is append-only.
Even if the server is compromised, the audit trail shows exactly what happened.
Logs are automatically rotated and compressed.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from .config import cfg

logger = logging.getLogger("wp.audit")


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fd: Optional[int] = None
        self._ensure_log_exists()

    def _ensure_log_exists(self):
        if not self.path.exists():
            self.path.touch(mode=0o600)

    def _rotate_if_needed(self):
        if self.path.stat().st_size > 100 * 1024 * 1024:
            rotated = self.path.with_suffix(f".{int(time.time())}.jsonl.gz")
            import gzip
            import shutil
            with open(self.path, "rb") as f_in:
                with gzip.open(rotated, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            self.path.unlink()
            self._ensure_log_exists()
            logger.info(f"Audit log rotated: {rotated}")

    def log(self, action: str, actor: str = "", resource: str = "", detail: dict | None = None, ip: str = ""):
        entry = {
            "ts": time.time(),
            "action": action,
            "actor": actor,
            "resource": resource,
            "detail": detail or {},
            "ip": ip,
        }
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
                f.flush()
            self._rotate_if_needed()
        except Exception as e:
            logger.error(f"Audit write failed: {e}")

    def query(self, limit: int = 100, action: str = "", actor: str = "") -> list[dict]:
        if not self.path.exists():
            return []
        entries = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if action and entry.get("action") != action:
                    continue
                if actor and entry.get("actor") != actor:
                    continue
                entries.append(entry)
                if len(entries) >= limit:
                    break
        return entries

    def stats(self) -> dict:
        if not self.path.exists():
            return {"total_entries": 0, "file_size": 0}
        count = 0
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    count += 1
        return {"total_entries": count, "file_size": self.path.stat().st_size}


_audit: Optional[AuditLog] = None


def get_audit() -> AuditLog:
    global _audit
    if _audit is None:
        _audit = AuditLog(cfg.audit_path)
    return _audit
