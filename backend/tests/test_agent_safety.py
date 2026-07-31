"""Tests: Agent Safety — permission tiers, kill switch, spending limits, address book, HITL, audit trail."""

import os
import time
from unittest.mock import patch

# Use conftest.py's env vars — do NOT override WP_VAULT_PASSWORD or WP_DATA_DIR here
from core.agent_safety import (
    _period_start,
    address_book_list,
    address_book_remove,
    allowlist_add,
    audit_log,
    audit_trail,
    blocklist_add,
    check_action_allowed,
    check_address,
    check_spending_limit,
    confirm_action,
    get_tier,
    is_killed,
    is_write_action,
    kill_agent,
    list_limits,
    list_pending,
    record_spending,
    reject_action,
    request_confirmation,
    resurrect_agent,
    verify_audit_chain,
)

# ── Permission Tiers ──────────────────────────────────────────────────────────


def test_get_tier_default():
    tier = get_tier()
    assert tier == "exec"


def test_get_tier_read():
    with patch.dict(os.environ, {"WP_AGENT_TIER": "read"}):
        assert get_tier() == "read"


def test_get_tier_plan():
    with patch.dict(os.environ, {"WP_AGENT_TIER": "plan"}):
        assert get_tier() == "plan"


def test_check_action_allowed_exec():
    allowed, reason = check_action_allowed("wallet_generate")
    assert allowed is True
    assert reason == ""


def test_check_action_allowed_plan_write_blocked():
    with patch.dict(os.environ, {"WP_AGENT_TIER": "plan"}):
        allowed, reason = check_action_allowed("wallet_generate")
        assert allowed is False
        assert "not allowed" in reason
        assert "plan" in reason


def test_check_action_allowed_plan_plan_allowed():
    with patch.dict(os.environ, {"WP_AGENT_TIER": "plan"}):
        allowed, _ = check_action_allowed("agent_plan")
        assert allowed is True


def test_check_action_allowed_read_blocks_write():
    with patch.dict(os.environ, {"WP_AGENT_TIER": "read"}):
        allowed, reason = check_action_allowed("wallet_generate")
        assert allowed is False
        assert "read" in reason


def test_check_action_allowed_read_blocks_plan():
    with patch.dict(os.environ, {"WP_AGENT_TIER": "read"}):
        allowed, _ = check_action_allowed("agent_plan")
        assert allowed is False


def test_check_action_allowed_read_allows_other():
    with patch.dict(os.environ, {"WP_AGENT_TIER": "read"}):
        allowed, _ = check_action_allowed("get_balance")
        assert allowed is True


def test_check_action_allowed_unknown_tier():
    with patch.dict(os.environ, {"WP_AGENT_TIER": "god"}):
        allowed, reason = check_action_allowed("get_balance")
        assert allowed is False
        assert "Unknown" in reason


def test_is_write_action_true():
    assert is_write_action("wallet_generate") is True
    assert is_write_action("vault_delete") is True
    assert is_write_action("key_export") is True


def test_is_write_action_false():
    assert is_write_action("get_balance") is False
    assert is_write_action("list_wallets") is False


# ── Kill Switch ───────────────────────────────────────────────────────────────


def test_is_killed_false_by_default():
    assert is_killed() is False


def test_kill_agent():
    result = kill_agent(reason="test kill")
    assert result["killed"] is True
    assert result["reason"] == "test kill"
    assert "resurrection_key" in result
    assert is_killed() is True
    # Cleanup
    from core.agent_safety import KILL_FILE, KILL_KEY_FILE

    KILL_FILE.unlink(missing_ok=True)
    KILL_KEY_FILE.unlink(missing_ok=True)


def test_resurrect_agent():
    result = kill_agent(reason="test resurrect")
    key = result["resurrection_key"]
    r = resurrect_agent(key)
    assert r["resurrected"] is True
    assert is_killed() is False


def test_resurrect_agent_wrong_key():
    kill_agent(reason="test wrong key")
    r = resurrect_agent("wrong-key-here")
    assert "error" in r
    # Cleanup
    from core.agent_safety import KILL_FILE, KILL_KEY_FILE

    KILL_FILE.unlink(missing_ok=True)
    KILL_KEY_FILE.unlink(missing_ok=True)


def test_resurrect_agent_not_killed():
    from core.agent_safety import KILL_FILE, KILL_KEY_FILE

    KILL_FILE.unlink(missing_ok=True)
    KILL_KEY_FILE.unlink(missing_ok=True)
    r = resurrect_agent("somekey")
    assert "error" in r


# ── Spending Limits ───────────────────────────────────────────────────────────


def test_period_start_daily():
    start = _period_start("daily")
    assert isinstance(start, float)
    assert start > 0
    assert start <= time.time()


def test_period_start_weekly():
    start = _period_start("weekly")
    assert isinstance(start, float)
    assert start > 0


def test_period_start_monthly():
    start = _period_start("monthly")
    assert isinstance(start, float)
    assert start > 0


def test_period_start_unknown():
    now = time.time()
    start = _period_start("yearly")
    assert abs(start - now) < 2  # close to current time


def test_check_spending_limit_no_limits():
    result = check_spending_limit("eth", 5.0)
    assert result["allowed"] is True
    assert "limits" in result
    assert result["limits"] == {}


def test_check_spending_limit_with_limit():
    with patch.dict(os.environ, {"WP_AGENT_LIMIT_ETH_DAILY": "10"}):
        result = check_spending_limit("eth", 5.0)
        assert result["allowed"] is True
        assert "daily" in result["limits"]


def test_check_spending_limit_exceeded():
    with patch.dict(os.environ, {"WP_AGENT_LIMIT_ETH_DAILY": "1"}):
        result = check_spending_limit("eth", 5.0)
        assert result["allowed"] is False
        assert "exceeded" in result


def test_record_spending():
    with patch.dict(os.environ, {"WP_AGENT_LIMIT_ETH_DAILY": "10"}):
        record_spending("eth_test_rec", 3.0)
        result = check_spending_limit("eth_test_rec", 2.0)
        assert result["allowed"] is True


def test_list_limits():
    record_spending("list_test_chain", 1.5)
    record_spending("list_test_chain", 2.5)
    result = list_limits()
    assert "usage" in result
    assert "list_test_chain" in result["usage"]


# ── Address Book ──────────────────────────────────────────────────────────────


def test_allowlist_add():
    result = allowlist_add("0xabc123", "eth", "my wallet")
    assert result["added"] is True
    assert result["list"] == "allowlist"


def test_blocklist_add():
    result = blocklist_add("0xdeadbeef", "eth", "scam")
    assert result["added"] is True
    assert result["list"] == "blocklist"


def test_address_book_list_all():
    allowlist_add("0xaaa111", "eth", "test1")
    blocklist_add("0xbbb222", "eth", "test2")
    entries = address_book_list()
    assert len(entries) >= 2


def test_address_book_list_filtered():
    allowlist_add("0xccc333", "eth", "filter_test")
    allow = address_book_list(list_type="allowlist")
    assert all(e["list_type"] == "allowlist" for e in allow)


def test_address_book_remove():
    allowlist_add("0xremoveme", "eth", "to_remove")
    result = address_book_remove("0xremoveme", "eth")
    assert result["removed"] is True


def test_address_book_remove_nonexistent():
    result = address_book_remove("0xnobody", "eth")
    assert result["removed"] is False


def test_check_address_allowed():
    result = check_address("0xfriend", "eth")
    assert result["allowed"] is True
    assert result["lists"] == []


def test_check_address_blocked():
    blocklist_add("0xbadactor", "eth", "known_scammer")
    result = check_address("0xbadactor", "eth")
    assert result["allowed"] is False
    assert "blocklist" in result["lists"]


def test_check_address_require_allowlist():
    allowlist_add("0xallowed1", "eth", "ok")
    with patch.dict(os.environ, {"WP_AGENT_REQUIRE_ALLOWLIST": "1"}):
        result_ok = check_address("0xallowed1", "eth")
        assert result_ok["allowed"] is True
        result_blocked = check_address("0xunknown", "eth")
        assert result_blocked["allowed"] is False


# ── HITL ──────────────────────────────────────────────────────────────────────


def test_request_confirmation():
    result = request_confirmation("wallet_generate", {"count": 3}, reason="test")
    assert "confirmation_id" in result
    assert result["status"] == "pending"
    assert result["ttl_seconds"] == 900


def test_confirm_action():
    req = request_confirmation("test_action", {"key": "val"}, reason="confirm test")
    cid = req["confirmation_id"]
    result = confirm_action(cid, "tester")
    assert result["approved"] is True
    assert result["params"]["key"] == "val"
    assert result["action"] == "test_action"


def test_confirm_action_not_found():
    result = confirm_action("nonexistent_id")
    assert "error" in result


def test_confirm_action_already_confirmed():
    req = request_confirmation("some_action", {"a": 1})
    cid = req["confirmation_id"]
    confirm_action(cid, "tester")
    result = confirm_action(cid, "tester2")
    assert "error" in result


def test_reject_action():
    req = request_confirmation("bad_action", {"x": 1}, reason="test reject")
    cid = req["confirmation_id"]
    result = reject_action(cid, "not needed")
    assert result["rejected"] is True


def test_reject_action_not_found():
    result = reject_action("fake_id")
    assert "error" in result


def test_confirm_action_expired():
    now = time.time()
    with patch("core.agent_safety.time.time") as mock_time:
        mock_time.return_value = now
        req = request_confirmation("expiring_action", {"x": 1}, ttl=1)
        cid = req["confirmation_id"]
        # Advance time past expiry
        mock_time.return_value = now + 100
        result = confirm_action(cid, "tester")
        assert "error" in result
        assert "expired" in result["error"].lower()


def test_list_pending():
    request_confirmation("pending_action", {"p": 1}, reason="list_test")
    pending = list_pending()
    assert any(p["action"] == "pending_action" for p in pending)


# ── Audit Trail ───────────────────────────────────────────────────────────────


def test_audit_log_and_trail():
    audit_log("test_action", {"param": 1}, {"result": "ok"}, confirmed_by="tester")
    entries = audit_trail(limit=10)
    assert len(entries) >= 1
    found = any(e["action"] == "test_action" for e in entries)
    assert found, "Audit entry not found in trail"


def test_verify_audit_chain_valid():
    audit_log("chain_test", {"x": 1}, {"y": 2})
    result = verify_audit_chain()
    assert result["valid"] is True
    assert result["entries_checked"] >= 1


def test_verify_audit_chain_empty():
    result = verify_audit_chain()
    assert isinstance(result, dict)
    assert "valid" in result or "entries_checked" in result


# ── Scam DB ───────────────────────────────────────────────────────────────────


def test_check_scam_db_not_loaded_is_safe():
    result = check_address("0xclean_addr_12345", "eth")
    assert result["allowed"] is True


# ── HITL Actor Binding (WP-007) ───────────────────────────────────────────────


def test_set_actor_get_actor():
    from core.agent_safety import get_actor, set_actor

    set_actor("admin:key1")
    assert get_actor() == "admin:key1"
    set_actor("")
    assert get_actor() == ""


def test_request_confirmation_records_requested_by():
    from core.agent_safety import _get_hitl_db

    req = request_confirmation(
        "wallet_sweep",
        {"from_wallet_id": "w1", "to_address": "0x..."},
        reason="actor bind test",
        requested_by="admin:key1",
    )
    cid = req["confirmation_id"]
    row = (
        _get_hitl_db()
        .execute("SELECT requested_by FROM hitl_confirmations WHERE id = ?", (cid,))
        .fetchone()
    )
    assert row["requested_by"] == "admin:key1"


def test_request_confirmation_defaults_to_context_actor():
    from core.agent_safety import _get_hitl_db, set_actor

    set_actor("admin:ctx")
    try:
        req = request_confirmation("vault_delete", {"wallet_id": "w2"}, reason="ctx test")
        row = (
            _get_hitl_db()
            .execute(
                "SELECT requested_by FROM hitl_confirmations WHERE id = ?",
                (req["confirmation_id"],),
            )
            .fetchone()
        )
        assert row["requested_by"] == "admin:ctx"
    finally:
        set_actor("")


def test_confirm_action_different_actor_denied():
    req = request_confirmation(
        "wallet_sweep",
        {"from_wallet_id": "w3", "to_address": "0xattacker"},
        reason="deny test",
        requested_by="admin:key1",
    )
    cid = req["confirmation_id"]
    result = confirm_action(cid, confirmed_by="admin:attacker")
    assert "error" in result
    assert "different actor" in result["error"].lower()


def test_confirm_action_same_actor_allowed():
    req = request_confirmation(
        "wallet_sweep",
        {"from_wallet_id": "w4", "to_address": "0xlegit"},
        reason="allow test",
        requested_by="admin:key1",
    )
    cid = req["confirmation_id"]
    result = confirm_action(cid, confirmed_by="admin:key1")
    assert result["approved"] is True
    assert result["action"] == "wallet_sweep"


def test_confirm_action_context_actor_flow():
    """End-to-end: context actor binds request, only same actor confirms."""
    from core.agent_safety import set_actor

    set_actor("env_admin")
    try:
        req = request_confirmation("key_export", {"wallet_id": "w5"}, reason="flow test")
        cid = req["confirmation_id"]
        # A different actor attempting to confirm is denied...
        denied = confirm_action(cid, confirmed_by="human")
        assert "error" in denied
        # ...the bound actor can confirm.
        result = confirm_action(cid, confirmed_by="env_admin")
        assert result["approved"] is True
    finally:
        set_actor("")
