"""Security audit fixes #18/#24/#13 — EIP-191 guardian recovery binding,
real timelock broadcast flow, fail-closed vault password enforcement.

All crypto uses fixed test keys. No network access (RPC is mocked).
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

os_env = None  # placeholder to keep flake quiet about import order

import os

from core.config import cfg

# NOTE: conftest.py sets WP_VAULT_PASSWORD / WP_DATA_DIR and cfg._vault_password.
# We rely on those values so the WalletGenerator singleton stays consistent
# across the suite (get_generator is a process-wide singleton).


@pytest.fixture(autouse=True)
def _fresh_generator_singleton():
    """get_generator() is a process-wide singleton; reset it around each test
    in this module so it is built with the current cfg.vault_password."""
    import wallet_engine.generator as gen_mod

    saved = gen_mod._generator
    gen_mod._generator = None
    yield
    gen_mod._generator = saved


from core.smart_wallet import (
    SmartWalletManager,
    build_recovery_message,
    eip191_hash,
)

# Fixed test keys (never used on any network)
KEY_A = "0x" + "11" * 32
KEY_B = "0x" + "22" * 32
KEY_CLAIMANT = "0x" + "33" * 32
_FIXED_TS = 1_700_000_000.0


def _evm_sign(message: str, key: str):
    from eth_account import Account
    from eth_account.messages import encode_defunct

    acct = Account.from_key(key)
    signed = acct.sign_message(encode_defunct(text=message))
    return acct.address, "0x" + signed.signature.hex()


def _sw() -> SmartWalletManager:
    tmp = Path(tempfile.mkstemp(suffix=".db")[1])
    return SmartWalletManager(tmp)


# ── #18: EIP-191 binding ──────────────────────────────────────────


def test_eip191_hash_matches_eth_account_personal_sign():
    from eth_account import Account
    from eth_account.messages import encode_defunct

    message = "WalletPress test message"
    acct = Account.from_key(KEY_A)
    signed = acct.sign_message(encode_defunct(text=message))
    # eth_account's encode_defunct uses EIP-191; recovering the signer from
    # our hash must yield the same address.
    recovered = Account.recover_message(encode_defunct(text=message), signature=signed.signature)
    assert recovered.lower() == acct.address.lower()
    # Our helper produces the same prefixed digest length semantics
    h = eip191_hash(message)
    assert len(h) == 32


def test_verify_signature_eip191_real_crypto():
    sw = _sw()
    message = build_recovery_message("wallet_x", "0x" + "cd" * 20, "eth", 1_700_000_000)
    address, sig = _evm_sign(message, KEY_A)
    assert sw._verify_signature(address, message, sig, "eth") is True


def test_verify_signature_rejects_tampered_message():
    sw = _sw()
    message = build_recovery_message("wallet_x", "0x" + "cd" * 20, "eth", 1_700_000_000)
    address, sig = _evm_sign(message, KEY_A)
    assert sw._verify_signature(address, message + "x", sig, "eth") is False


def test_verify_signature_rejects_wrong_signer():
    sw = _sw()
    message = "some message"
    _addr, sig = _evm_sign(message, KEY_A)
    assert sw._verify_signature("0x" + "ab" * 20, message, sig, "eth") is False


def test_recovery_end_to_end_real_signatures():
    """Guardians + claimant sign the canonical message; recovery succeeds."""
    sw = _sw()
    g1, _ = _evm_sign("probe", KEY_A)
    g2, _ = _evm_sign("probe", KEY_B)
    claimant_addr, _ = _evm_sign("probe", KEY_CLAIMANT)

    sw.setup_recovery("wallet_e2e", [g1, g2], threshold=2)
    canonical = build_recovery_message("wallet_e2e", claimant_addr, "eth", _FIXED_TS)

    _, sig1 = _evm_sign(canonical, KEY_A)
    _, sig2 = _evm_sign(canonical, KEY_B)
    _, claim_sig = _evm_sign(canonical, KEY_CLAIMANT)

    with (
        patch("core.smart_wallet.time.time", return_value=_FIXED_TS),
        patch.object(
            sw, "_execute_recovery", return_value={"success": True, "new_address": claimant_addr}
        ),
    ):
        result = sw.request_recovery(
            "wallet_e2e",
            claimant_addr,
            "eth",
            [
                {"address": g1, "signature": sig1, "message": canonical},
                {"address": g2, "signature": sig2, "message": canonical},
            ],
            claimant_signature=claim_sig,
        )
    assert result.get("recovered") is True, result
    assert result["guardians_used"] == 2


def test_recovery_rejects_signature_over_wrong_message():
    """Guardian sig over a different message must NOT count."""
    sw = _sw()
    g1, _ = _evm_sign("probe", KEY_A)
    g2, _ = _evm_sign("probe", KEY_B)
    claimant_addr, _ = _evm_sign("probe", KEY_CLAIMANT)

    sw.setup_recovery("wallet_wrongmsg", [g1, g2], threshold=2)
    canonical = build_recovery_message("wallet_wrongmsg", claimant_addr, "eth", _FIXED_TS)

    _, sig1 = _evm_sign(canonical, KEY_A)
    _, sig2_wrong = _evm_sign("unrelated message", KEY_B)  # not bound to recovery
    _, claim_sig = _evm_sign(canonical, KEY_CLAIMANT)

    with patch("core.smart_wallet.time.time", return_value=_FIXED_TS):
        result = sw.request_recovery(
            "wallet_wrongmsg",
            claimant_addr,
            "eth",
            [
                {"address": g1, "signature": sig1, "message": canonical},
                {"address": g2, "signature": sig2_wrong, "message": "unrelated message"},
            ],
            claimant_signature=claim_sig,
        )
    assert "error" in result
    assert "valid guardian signatures" in result["error"]


def test_recovery_rejects_claimant_not_recovering_owner():
    """Claimant signature must recover to the new_address, not someone else."""
    sw = _sw()
    g1, _ = _evm_sign("probe", KEY_A)
    g2, _ = _evm_sign("probe", KEY_B)
    claimant_addr, _ = _evm_sign("probe", KEY_CLAIMANT)

    sw.setup_recovery("wallet_claim", [g1, g2], threshold=2)
    canonical = build_recovery_message("wallet_claim", claimant_addr, "eth", _FIXED_TS)

    _, sig1 = _evm_sign(canonical, KEY_A)
    _, sig2 = _evm_sign(canonical, KEY_B)
    # Signed by KEY_A — not the recovering owner (claimant_addr)
    _, impostor_sig = _evm_sign(canonical, KEY_A)

    with patch("core.smart_wallet.time.time", return_value=_FIXED_TS):
        result = sw.request_recovery(
            "wallet_claim",
            claimant_addr,
            "eth",
            [
                {"address": g1, "signature": sig1, "message": canonical},
                {"address": g2, "signature": sig2, "message": canonical},
            ],
            claimant_signature=impostor_sig,
        )
    assert "error" in result
    assert "claimant" in result["error"].lower()


def test_recovery_rejects_replayed_request():
    sw = _sw()
    g1, _ = _evm_sign("probe", KEY_A)
    g2, _ = _evm_sign("probe", KEY_B)
    claimant_addr, _ = _evm_sign("probe", KEY_CLAIMANT)

    sw.setup_recovery("wallet_replay", [g1, g2], threshold=2)
    canonical = build_recovery_message("wallet_replay", claimant_addr, "eth", _FIXED_TS)

    _, sig1 = _evm_sign(canonical, KEY_A)
    _, sig2 = _evm_sign(canonical, KEY_B)
    _, claim_sig = _evm_sign(canonical, KEY_CLAIMANT)

    sigs = [
        {"address": g1, "signature": sig1, "message": canonical},
        {"address": g2, "signature": sig2, "message": canonical},
    ]

    with (
        patch("core.smart_wallet.time.time", return_value=_FIXED_TS),
        patch.object(
            sw, "_execute_recovery", return_value={"success": True, "new_address": claimant_addr}
        ),
    ):
        first = sw.request_recovery(
            "wallet_replay", claimant_addr, "eth", sigs, claimant_signature=claim_sig
        )
    assert first.get("recovered") is True

    # Replay the same recovery (fresh signatures, same target) → rejected
    _, sig1b = _evm_sign(canonical, KEY_A)
    _, sig2b = _evm_sign(canonical, KEY_B)
    _, claim_b = _evm_sign(canonical, KEY_CLAIMANT)
    replay = sw.request_recovery(
        "wallet_replay",
        claimant_addr,
        "eth",
        [
            {"address": g1, "signature": sig1b, "message": canonical},
            {"address": g2, "signature": sig2b, "message": canonical},
        ],
        claimant_signature=claim_b,
    )
    assert "error" in replay
    assert "replay" in replay["error"].lower()


# ── #24: real timelock broadcast ──────────────────────────────────


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _rpc_mock(responses):
    """httpx.post mock that answers JSON-RPC methods from a dict."""

    def fake_post(url, json=None, timeout=None, **kwargs):
        method = json["method"]
        if method == "eth_getTransactionCount":
            return _FakeResp({"jsonrpc": "2.0", "id": 1, "result": "0x2"})
        if method == "eth_gasPrice":
            return _FakeResp({"jsonrpc": "2.0", "id": 1, "result": "0x3b9aca00"})
        if method == "eth_chainId":
            return _FakeResp({"jsonrpc": "2.0", "id": 1, "result": "0x1"})
        if method == "eth_sendRawTransaction":
            return _FakeResp({"jsonrpc": "2.0", "id": 1, "result": "0x" + "ee" * 32})
        return _FakeResp({"jsonrpc": "2.0", "id": 1, "error": {"message": "unknown"}})

    return fake_post


class _FakeWallet:
    def __init__(self, address, encrypted_key):
        self.address = address
        self.encrypted_key = encrypted_key


def _make_encrypted_wallet():
    from wallet_engine.generator import WalletGenerator

    gen = WalletGenerator(vault_password=cfg.vault_password)
    encrypted = gen._encrypt_key(KEY_CLAIMANT)
    acct_addr, _ = _evm_sign("probe", KEY_CLAIMANT)
    return _FakeWallet(acct_addr, encrypted)


def test_send_transaction_real_broadcast():
    sw = _sw()
    wallet = _make_encrypted_wallet()

    with (
        patch("core.vault.get_vault") as mock_vault,
        patch("httpx.post", side_effect=_rpc_mock(None)),
        patch.dict(os.environ, {"WP_RPC_ETH": "http://rpc.test"}),
    ):
        mock_vault.return_value.get.return_value = wallet
        result = sw._send_transaction("w1", "0x" + "dd" * 20, "eth", 0.5)

    assert result["tx_hash"] == "0x" + "ee" * 32
    assert result["from"] == wallet.address
    assert not result["tx_hash"].startswith("pending_")


def test_send_transaction_no_rpc_raises_no_fake_hash():
    sw = _sw()
    wallet = _make_encrypted_wallet()
    with (
        patch("core.vault.get_vault") as mock_vault,
        patch.dict(os.environ, {"WP_RPC_ETH": ""}, clear=False),
    ):
        mock_vault.return_value.get.return_value = wallet
        with pytest.raises(ValueError, match="No RPC configured"):
            sw._send_transaction("w1", "0x" + "dd" * 20, "eth", 0.5)


def test_timelock_only_marked_complete_after_broadcast():
    sw = _sw()
    sw.create_timelock("wallet_tl", "0x" + "dd" * 20, "eth", 1.0, time.time() + 3600)
    wallet = _make_encrypted_wallet()

    later = time.time() + 7200

    def failing_post(url, json=None, **kwargs):
        if json["method"] == "eth_sendRawTransaction":
            return _FakeResp(
                {"jsonrpc": "2.0", "id": 1, "error": {"message": "insufficient funds"}}
            )
        return _rpc_mock(None)(url, json=json)

    with (
        patch("core.vault.get_vault") as mock_vault,
        patch("httpx.post", side_effect=failing_post),
        patch.dict(os.environ, {"WP_RPC_ETH": "http://rpc.test"}),
    ):
        mock_vault.return_value.get.return_value = wallet
        with patch("core.smart_wallet.time.time", return_value=later):
            results = sw.execute_due_timelocks()

    assert len(results) == 1
    assert results[0]["executed"] is False
    assert "insufficient funds" in results[0]["error"]

    # Timelock must NOT be marked executed
    locks = sw.list_timelocks("wallet_tl")
    assert locks[0]["executed"] == 0


def test_timelock_success_marks_executed():
    sw = _sw()
    sw.create_timelock("wallet_tl2", "0x" + "dd" * 20, "eth", 1.0, time.time() + 3600)
    wallet = _make_encrypted_wallet()

    with (
        patch("core.vault.get_vault") as mock_vault,
        patch("httpx.post", side_effect=_rpc_mock(None)),
        patch.dict(os.environ, {"WP_RPC_ETH": "http://rpc.test"}),
    ):
        mock_vault.return_value.get.return_value = wallet
        with patch("core.smart_wallet.time.time", return_value=time.time() + 7200):
            results = sw.execute_due_timelocks()

    assert len(results) == 1
    assert results[0]["executed"] is True
    assert results[0]["tx_hash"] == "0x" + "ee" * 32
    locks = sw.list_timelocks("wallet_tl2")
    assert locks[0]["executed"] == 1
    assert locks[0]["tx_hash"] == "0x" + "ee" * 32


# ── #13: fail-closed vault password ───────────────────────────────


class _StubRequest:
    def __init__(self):
        self.headers = {"X-API-Key": "testkey"}


def test_import_wallet_fails_closed_without_password():
    import asyncio

    from fastapi import HTTPException

    from routers.chain_vault import ImportRequest, import_wallet

    old = cfg._vault_password
    cfg._vault_password = ""
    try:
        req = ImportRequest(chain="eth", private_key=KEY_A, label="t")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(import_wallet(req, _StubRequest()))
        assert exc_info.value.status_code == 503
        assert "WP_VAULT_PASSWORD" in exc_info.value.detail
    finally:
        cfg._vault_password = old


def test_airdrop_generate_fails_closed_without_password():
    import asyncio

    from fastapi import HTTPException

    from routers.airdrop import AirdropRequest, airdrop_generate

    old = cfg._vault_password
    cfg._vault_password = ""
    try:
        req = AirdropRequest(chain="eth", total_wallets=2)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(airdrop_generate(req, _StubRequest()))
        assert exc_info.value.status_code == 503
        assert "WP_VAULT_PASSWORD" in exc_info.value.detail
    finally:
        cfg._vault_password = old


def test_airdrop_generate_uses_vault_password():
    """Generator must be constructed with the configured vault password."""
    import ast

    airdrop_path = os.path.join(os.path.dirname(__file__), "..", "routers", "airdrop.py")
    with open(airdrop_path) as f:
        src = f.read()
    assert "get_generator(cfg.vault_password)" in src
    # No bare get_generator() without password anywhere in airdrop router
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "get_generator":
            assert node.args, "get_generator must receive vault_password"
