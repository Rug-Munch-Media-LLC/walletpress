"""Tests: config, license manager, JWT auth."""

import base64
import hashlib
import hmac
import json
import os
import tempfile
import time
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-pw-clj"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_clj_")

import pytest

from core.config import cfg, Config, _check_key_file_perms
from core.license import LicenseManager, FEATURES, get_license
from core.jwt_auth import _load_key, validate_rmi_jwt


# ── Config tests ────────────────────────────────────────────────────


def test_rpc_url_default():
    url = Config.rpc_url("eth", "https://eth.llamarpc.com")
    assert url == "https://eth.llamarpc.com"


def test_rpc_url_env_override(monkeypatch):
    monkeypatch.setenv("WP_RPC_ETH", "https://custom.eth.node")
    url = Config.rpc_url("eth", "https://eth.llamarpc.com")
    assert url == "https://custom.eth.node"


def test_rpc_urls_returns_dict():
    urls = Config.rpc_urls()
    assert isinstance(urls, dict)
    assert "eth" in urls
    assert "sol" in urls
    assert "trx" in urls
    assert urls["eth"]  # non-empty


def test_vault_password_property():
    assert hasattr(cfg, "vault_password")


def test_clear_vault_password():
    old = cfg._vault_password
    try:
        cfg.clear_vault_password()
        assert cfg.vault_password == ""
    finally:
        cfg._vault_password = old


def test_rotate_vault_key(tmp_path):
    old = cfg._vault_password
    try:
        key_dir = tmp_path / ".walletpress"
        key_dir.mkdir(parents=True)
        key_file = key_dir / "vault.key"
        # Temporarily swap vault_key_path
        orig_path = cfg.vault_key_path
        cfg.vault_key_path = key_file

        cfg.rotate_vault_key()
        assert key_file.exists()
        assert cfg._vault_password != ""

        cfg.vault_key_path = orig_path
    finally:
        cfg._vault_password = old


def test_check_key_file_perms(tmp_path):
    kf = tmp_path / "test.key"
    kf.write_text("test-key-content")
    os.chmod(kf, 0o600)
    assert _check_key_file_perms(kf) is True


# ── LicenseManager tests ────────────────────────────────────────────


def _make_license_token(tier: str, exp: int, secret: str) -> str:
    payload = json.dumps({"tier": tier, "exp": exp}, sort_keys=True)
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token_data = json.dumps({"tier": tier, "exp": exp, "sig": sig})
    return base64.b64encode(token_data.encode()).decode()


def test_license_defaults_to_community(monkeypatch):
    monkeypatch.delenv("WP_LICENSE_KEY", raising=False)
    monkeypatch.delenv("WP_ADMIN_KEY", raising=False)
    monkeypatch.delenv("WP_LICENSE_SECRET", raising=False)
    lm = LicenseManager(key_path=Path("/nonexistent/license.key"))
    assert lm.tier == "community"
    assert lm.is_paid is False


def test_license_verify_valid_token(monkeypatch):
    monkeypatch.setenv("WP_LICENSE_SECRET", "test-license-secret")
    future = int(time.time()) + 86400 * 365
    token = _make_license_token("pro", future, "test-license-secret")
    lm = LicenseManager(key_path=Path("/nonexistent/license.key"))
    result = lm._verify_token(token)
    assert result == "pro"


def test_license_verify_expired_token(monkeypatch):
    monkeypatch.setenv("WP_LICENSE_SECRET", "test-license-secret")
    past = int(time.time()) - 86400
    token = _make_license_token("pro", past, "test-license-secret")
    lm = LicenseManager(key_path=Path("/nonexistent/license.key"))
    assert lm._verify_token(token) is None


def test_license_verify_bad_signature(monkeypatch):
    monkeypatch.setenv("WP_LICENSE_SECRET", "test-license-secret")
    future = int(time.time()) + 86400 * 365
    token = _make_license_token("pro", future, "wrong-secret")
    lm = LicenseManager(key_path=Path("/nonexistent/license.key"))
    assert lm._verify_token(token) is None


def test_license_verify_invalid_tier(monkeypatch):
    monkeypatch.setenv("WP_LICENSE_SECRET", "test-license-secret")
    future = int(time.time()) + 86400 * 365
    token = _make_license_token("nonexistent_tier", future, "test-license-secret")
    lm = LicenseManager(key_path=Path("/nonexistent/license.key"))
    assert lm._verify_token(token) is None


def test_license_has_feature_community():
    lm = LicenseManager(key_path=Path("/nonexistent/license.key"))
    assert lm.has_feature("wallet_generation") is True
    assert lm.has_feature("two_factor_auth") is False


def test_license_to_dict():
    lm = LicenseManager(key_path=Path("/nonexistent/license.key"))
    d = lm.to_dict()
    assert d["tier"] == "community"
    assert d["is_paid"] is False
    assert "features" in d
    assert "max_vault_wallets" in d


def test_license_check_wallet_limit():
    lm = LicenseManager(key_path=Path("/nonexistent/license.key"))
    # Community limit is 10
    assert lm.check_wallet_limit(5) is True
    assert lm.check_wallet_limit(10) is False


def test_license_check_batch_limit():
    lm = LicenseManager(key_path=Path("/nonexistent/license.key"))
    assert lm.check_batch_limit(1) is True
    assert lm.check_batch_limit(2) is False


def test_get_license_singleton():
    lm1 = get_license()
    lm2 = get_license()
    assert lm1 is lm2


# ── JWT auth tests ──────────────────────────────────────────────────


def test_load_key_from_file(tmp_path):
    kf = tmp_path / "key.pem"
    kf.write_text("-----BEGIN PUBLIC KEY-----\nTESTKEY\n-----END PUBLIC KEY-----")
    result = _load_key(str(kf))
    assert "BEGIN PUBLIC KEY" in result
    assert "TESTKEY" in result


def test_load_key_from_string():
    pem = "-----BEGIN PUBLIC KEY-----\nDIRECTKEY\n-----END PUBLIC KEY-----"
    result = _load_key(pem)
    assert result == pem


def test_validate_rmi_jwt_none():
    assert validate_rmi_jwt("") is None


def test_validate_rmi_jwt_invalid():
    result = validate_rmi_jwt("invalid.jwt.token")
    assert result is None
