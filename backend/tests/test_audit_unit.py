"""Tests: AuditLog operations."""

import os
import tempfile
import json
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-audit"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_audit_")

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from core.audit import AuditLog


def test_log_and_query():
    path = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    audit = AuditLog(path)
    audit.log("wallet.generate", actor="test-user", resource="eth")
    entries = audit.query()
    assert len(entries) == 1
    assert entries[0]["action"] == "wallet.generate"
    assert entries[0]["actor"] == "test-user"
    assert entries[0]["resource"] == "eth"
    assert "ts" in entries[0]


def test_log_with_detail():
    path = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    audit = AuditLog(path)
    audit.log("test.action", detail={"key": "value", "count": 42})
    entries = audit.query()
    assert entries[0]["detail"]["key"] == "value"
    assert entries[0]["detail"]["count"] == 42


def test_query_with_filter():
    path = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    audit = AuditLog(path)
    audit.log("wallet.generate", actor="alice")
    audit.log("wallet.delete", actor="bob")
    audit.log("wallet.generate", actor="bob")
    alice_entries = audit.query(action="wallet.generate", actor="alice")
    assert len(alice_entries) == 1
    bob_gen = audit.query(action="wallet.generate", actor="bob")
    assert len(bob_gen) == 1
    all_generate = audit.query(action="wallet.generate")
    assert len(all_generate) == 2


def test_query_limit():
    path = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    audit = AuditLog(path)
    for i in range(10):
        audit.log("test", actor=f"user{i}")
    limited = audit.query(limit=3)
    assert len(limited) == 3
    full = audit.query(limit=100)
    assert len(full) == 10


def test_query_empty():
    path = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    audit = AuditLog(path)
    assert audit.query() == []


def test_query_nonexistent_file():
    path = Path("/tmp/nonexistent_audit_file_xyz.jsonl")
    audit = AuditLog(path)
    entries = audit.query()
    assert entries == []


def test_stats_empty():
    path = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    audit = AuditLog(path)
    stats = audit.stats()
    assert stats["total_entries"] == 0
    assert stats["file_size"] == 0


def test_stats_with_entries():
    path = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    audit = AuditLog(path)
    audit.log("test")
    audit.log("test2")
    stats = audit.stats()
    assert stats["total_entries"] == 2
    assert stats["file_size"] > 0


def test_log_includes_ip():
    path = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    audit = AuditLog(path)
    audit.log("test", actor="alice", ip="192.168.1.1")
    entries = audit.query()
    assert entries[0]["ip"] == "192.168.1.1"


def test_log_persists_to_disk():
    path = Path(tempfile.mkstemp(suffix=".jsonl")[1])
    audit1 = AuditLog(path)
    audit1.log("persistent", actor="test")
    audit2 = AuditLog(path)
    entries = audit2.query()
    assert len(entries) == 1
    assert entries[0]["action"] == "persistent"


def test_ensure_log_creates_file():
    path = Path(tempfile.mkdtemp()) / "new_audit.jsonl"
    audit = AuditLog(path)
    assert path.exists()
    audit.log("first_entry")
    assert path.stat().st_size > 0
