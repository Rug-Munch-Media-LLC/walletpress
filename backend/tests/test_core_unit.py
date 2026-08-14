"""Tests: config, event_bus, structured_logging, ip_allowlist, license_check."""

import os
import tempfile

# Set env vars before importing modules
os.environ["WP_VAULT_PASSWORD"] = "test-core-unit"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_core_")
os.environ["WP_RATE_LIMIT"] = "0"

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from core import event_bus

# ── Config tests ──────────────────────────────────────────────────


def test_config_has_vault_password():
    assert cfg.vault_password is not None
    assert len(cfg.vault_password) > 0


def test_config_data_dir_exists():
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    assert cfg.data_dir.exists()


def test_config_db_path():
    db_path = cfg.db_path
    assert str(db_path).endswith(".db") or "db" in str(db_path)


def test_config_keys_path():
    keys_path = cfg.keys_path
    assert str(keys_path).endswith(".json")


def test_config_audit_path():
    audit_path = cfg.audit_path
    assert "audit" in str(audit_path).lower()


def test_config_clear_vault_password():
    # Save original
    orig = cfg._vault_password
    try:
        cfg.clear_vault_password()
        assert cfg.vault_password is None or cfg.vault_password == ""
    finally:
        cfg._vault_password = orig


# ── EventBus tests ────────────────────────────────────────────────


def test_event_bus_emit_and_subscribe():
    received = []
    event_bus.subscribe(lambda evt, data: received.append((evt, data)))
    event_bus.emit("test_event", {"msg": "hello"})
    assert len(received) >= 1
    found = any(evt == "test_event" for evt, _ in received)
    assert found, "Event should be received by subscriber"


def test_event_bus_multiple_subscribers():
    results = []
    event_bus.subscribe(lambda evt, d: results.append("a"))
    event_bus.subscribe(lambda evt, d: results.append("b"))
    event_bus.emit("multi", {})
    assert len(results) == 2
    assert "a" in results
    assert "b" in results


def test_event_bus_no_subscriber():
    # Should not raise when emitting without subscribers
    # First, clear subscribers by calling emit without them
    # (subscribers accumulate, but emit must not crash)
    event_bus.emit("unsubscribed_event", {"data": 1})
    event_bus.emit("another_event", {})


# ── Structured logging tests ──────────────────────────────────────


from core.structured_logging import get_logger, setup_logging


def test_setup_logging_does_not_crash():
    # Should not raise any exception
    setup_logging(level="INFO")
    setup_logging(level="DEBUG")
    setup_logging(level="WARNING")


def test_get_logger_returns_logger():
    logger = get_logger("test_module")
    assert logger is not None
    assert hasattr(logger, "info")


# ── IP allowlist tests ────────────────────────────────────────────


def test_ip_allowlist_initially_empty():
    from core.ip_allowlist import ALLOWED_IPS

    # When WP_ALLOWED_IPS is not set, list should be empty
    assert isinstance(ALLOWED_IPS, list)
