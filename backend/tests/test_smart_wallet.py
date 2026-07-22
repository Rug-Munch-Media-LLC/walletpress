"""Tests: Smart Wallet -- social recovery, dead man's switch, timelocks."""
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from Crypto.Hash import keccak  # noqa: F401  # ensure keccak is loadable for patch

os.environ["WP_VAULT_PASSWORD"] = "test-vault-password"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_sw_")

from core.config import cfg
cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from core.smart_wallet import SmartWalletManager


def _sw() -> SmartWalletManager:
    tmp = Path(tempfile.mkstemp(suffix=".db")[1])
    return SmartWalletManager(tmp)


def _sig(address: str) -> dict:
    return {
        "address": address,
        "signature": "0x" + "ab" * 65,
        "message": "test",
    }


def test_setup_recovery():
    sw = _sw()
    guardians = [
        "0x1111111111111111111111111111111111111111",
        "0x2222222222222222222222222222222222222222",
        "0x3333333333333333333333333333333333333333",
    ]
    result = sw.setup_recovery("wallet_r1", guardians, threshold=2)
    assert "error" not in result
    assert result["wallet_id"] == "wallet_r1"
    assert result["threshold"] == 2
    assert result["guardians"] == guardians

    config = sw.get_recovery_config("wallet_r1")
    assert config is not None
    assert config["guardians"] == guardians
    assert config["threshold"] == 2

    err = sw.setup_recovery("wallet_bad", ["0xa"], threshold=2)
    assert "error" in err


def test_request_recovery_with_insufficient_guardians():
    sw = _sw()
    sw.setup_recovery("wallet_r2", ["0xAAA", "0xBBB"], threshold=2)
    sigs = [_sig("0xAAA")]
    result = sw.request_recovery("wallet_r2", "0xNEW", "eth", sigs)
    assert "error" in result
    assert result.get("required") == 2
    assert result.get("provided") == 1


def test_request_recovery_with_sufficient_guardians():
    sw = _sw()
    guardians = ["0xAAA", "0xBBB", "0xCCC"]
    sw.setup_recovery("wallet_r3", guardians, threshold=2)
    sigs = [_sig("0xAAA"), _sig("0xBBB")]

    with patch.object(sw, "_verify_signature", return_value=True):
        with patch.object(
            sw, "_execute_recovery",
            return_value={"success": True, "new_address": "0xNEW"},
        ):
            result = sw.request_recovery(
                "wallet_r3", "0xNEW", "eth", sigs,
                claimant_signature="0xVALID",
            )

    assert result.get("recovered") is True
    assert result.get("success") or result.get("new_address")
    assert result["new_address"] == "0xNEW"
    assert result["guardians_used"] == 2


def test_recovery_requires_claimant_signature():
    sw = _sw()
    sw.setup_recovery("wallet_r4", ["0xAAA", "0xBBB"], threshold=2)
    sigs = [_sig("0xAAA"), _sig("0xBBB")]

    with patch.object(sw, "_verify_signature", return_value=True):
        result = sw.request_recovery(
            "wallet_r4", "0xNEW", "eth", sigs,
            claimant_signature="",
        )

    assert "error" in result
    assert "claimant" in result["error"].lower()


def test_recovery_with_invalid_claimant_signature():
    sw = _sw()
    guardians = ["0xAAA", "0xBBB"]
    sw.setup_recovery("wallet_r5", guardians, threshold=2)
    sigs = [_sig("0xAAA"), _sig("0xBBB")]

    with patch.object(sw, "_verify_signature") as mock_v:
        mock_v.side_effect = lambda addr, msg, sig, chain: (
            addr.lower() in [g.lower() for g in guardians]
        )
        result = sw.request_recovery(
            "wallet_r5", "0xNEW", "eth", sigs,
            claimant_signature="0xBAD",
        )

    assert "error" in result
    assert "invalid" in result["error"].lower() or "claimant" in result["error"].lower()


def test_setup_deadman():
    sw = _sw()
    result = sw.setup_deadman("wallet_d1", "0xHEIR", heir_chain="eth", timeout_days=90)
    assert "error" not in result
    assert result["activated"] is True
    assert result["heir_address"] == "0xHEIR"
    assert result["timeout_days"] == 90

    err = sw.setup_deadman("wallet_d2", "0xHEIR2", timeout_days=3)
    assert "error" in err

    err = sw.setup_deadman("wallet_d3", "0xHEIR3", timeout_days=800)
    assert "error" in err

    status = sw.check_deadman("wallet_d1")
    assert status["active"] is True
    assert status["triggered"] is False


def test_trigger_deadman_before_timer():
    sw = _sw()
    now = 1_000_000.0
    with patch("core.smart_wallet.time.time", return_value=now):
        sw.setup_deadman("wallet_d4", "0xHEIR", timeout_days=30)

    later = now + 5 * 86400
    with patch("core.smart_wallet.time.time", return_value=later):
        result = sw.trigger_deadman("wallet_d4", "0xHEIR", "0xSIG")

    assert "error" in result
    assert "remaining" in result.get("error", "").lower()


def test_trigger_deadman_after_timer():
    sw = _sw()
    now = 1_000_000.0
    with patch("core.smart_wallet.time.time", return_value=now):
        sw.setup_deadman("wallet_d5", "0xHEIR", heir_chain="eth", timeout_days=30)

    later = now + 35 * 86400
    with patch("core.smart_wallet.time.time", return_value=later):
        with patch.object(
            sw, "_execute_recovery",
            return_value={"success": True, "new_address": "0xNEW"},
        ):
            result = sw.trigger_deadman("wallet_d5", "0xHEIR", "0xSIG")

    assert result.get("triggered") is True
    assert result["heir_address"] == "0xHEIR"


def test_create_timelock():
    sw = _sw()
    future = time.time() + 3600
    result = sw.create_timelock("wallet_t1", "0xDEST", "eth", 1.5, future)
    assert "error" not in result
    assert result["amount"] == 1.5
    assert result["to_address"] == "0xDEST"

    locks = sw.list_timelocks("wallet_t1")
    assert len(locks) == 1
    assert locks[0]["id"] == result["timelock_id"]

    all_locks = sw.list_timelocks()
    assert len(all_locks) >= 1

    err = sw.create_timelock("wallet_t2", "0xDEST", "eth", 0.5, time.time() - 10)
    assert "error" in err


def test_timelock_not_executed_before_due():
    sw = _sw()
    future = time.time() + 3600
    sw.create_timelock("wallet_t3", "0xDEST", "eth", 0.5, future)

    due = sw.execute_due_timelocks()
    assert isinstance(due, list)
    assert len(due) == 0


def test_verify_signature_valid():
    sw = _sw()
    address = "0x" + "ab" * 20
    sig = "0x" + "ff" * 64 + "1b"

    with patch("eth_account.messages.defunct_hash_message", return_value=b"\x00" * 32), \
         patch("coincurve.PublicKey") as MockPK, \
         patch("Crypto.Hash.keccak") as MockKeccak:

        mock_pub = MagicMock()
        mock_pub.format.return_value = bytes.fromhex("04" + "00" * 32 + "ab" * 20)
        MockPK.from_signature_and_message.return_value = mock_pub

        mock_hash = MagicMock()
        mock_hash.digest.return_value = bytes.fromhex("00" * 12 + "ab" * 20)
        MockKeccak.new.return_value = mock_hash

        assert sw._verify_signature(address, "msg", sig, "eth") is True


def test_verify_signature_invalid():
    sw = _sw()
    address = "0x" + "ab" * 20
    sig = "0x" + "ff" * 64 + "1c"

    with patch("eth_account.messages.defunct_hash_message", return_value=b"\x00" * 32), \
         patch("coincurve.PublicKey") as MockPK, \
         patch("Crypto.Hash.keccak") as MockKeccak:

        mock_pub = MagicMock()
        mock_pub.format.return_value = bytes.fromhex("04" + "00" * 32 + "cd" * 20)
        MockPK.from_signature_and_message.return_value = mock_pub

        mock_hash = MagicMock()
        mock_hash.digest.return_value = bytes.fromhex("00" * 12 + "cd" * 20)
        MockKeccak.new.return_value = mock_hash

        assert sw._verify_signature(address, "msg", sig, "eth") is False


def test_verify_signature_empty_or_bad_length():
    sw = _sw()
    assert sw._verify_signature("", "msg", "0xsig", "eth") is False
    assert sw._verify_signature("0xABC", "msg", "", "eth") is False
    assert sw._verify_signature("0xABC", "msg", "0x1234", "eth") is False


def test_stats():
    sw = _sw()
    sw.setup_recovery("wallet_s1", ["0xA", "0xB", "0xC"], threshold=1)
    sw.setup_deadman("wallet_s2", "0xH", timeout_days=30)
    sw.create_timelock("wallet_s3", "0xD", "eth", 1.0, time.time() + 3600)
    s = sw.stats()
    assert s["recovery_configs"] >= 1
    assert s["deadman_switches"] >= 1
    assert s["timelocks_total"] >= 1
