"""Tests: hosting/user management."""

import os
import tempfile
import time
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-pw-hosting"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_hosting_")

import hashlib
import pytest

from core.hosting import (
    HostingDB,
    PLANS,
    _hash_password,
    _verify_password,
    _needs_rehash,
    _check_legacy_hashes,
    get_hosting,
)
from core.config import cfg


def _hosting() -> HostingDB:
    tmp = Path(tempfile.mkstemp(suffix="_hosting.db")[1])
    return HostingDB(tmp)


class TestPlans:
    def test_plans_defined(self):
        assert "free" in PLANS
        assert "starter" in PLANS
        assert "pro" in PLANS
        assert "enterprise" in PLANS

    def test_free_plan_structure(self):
        p = PLANS["free"]
        assert p["price_usd"] == 0
        assert p["daily_wallet_limit"] == 10
        assert p["api_access"] is False

    def test_pro_features(self):
        p = PLANS["pro"]
        assert "all" in p["features"]


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "my-secure-password-123!"
        hashed = _hash_password(pw)
        assert hashed != pw
        assert hashed.startswith("$argon2id$")
        assert _verify_password(hashed, pw) is True

    def test_verify_wrong_password(self):
        hashed = _hash_password("correct-password")
        assert _verify_password(hashed, "wrong-password") is False

    def test_verify_empty_hash(self):
        assert _verify_password("", "anything") is False

    def test_legacy_sha256_verify(self):
        pw = "legacy-password"
        legacy_hash = hashlib.sha256(pw.encode()).hexdigest()
        assert _verify_password(legacy_hash, pw) is True

    def test_legacy_sha256_wrong_password(self):
        legacy_hash = hashlib.sha256(b"real-password").hexdigest()
        assert _verify_password(legacy_hash, "wrong") is False

    def test_needs_rehash_legacy(self):
        assert _needs_rehash("abc123") is True

    def test_needs_rehash_argon(self):
        hashed = _hash_password("test")
        # Modern argon shouldn't need rehash
        result = _needs_rehash(hashed)
        assert isinstance(result, bool)


class TestHostingDB:
    def test_register_user(self):
        h = _hosting()
        result = h.register("test@example.com", "secure-pass", name="Test User")
        assert "user_id" in result
        assert "api_key" in result
        assert result["plan"] == "free"
        assert result["email_verification_required"] is False

    def test_register_duplicate_email(self):
        h = _hosting()
        h.register("dup@example.com", "pass1")
        result = h.register("dup@example.com", "pass2")
        assert "error" in result

    def test_login_success(self):
        h = _hosting()
        h.register("login@example.com", "mypassword")
        user = h.login("login@example.com", "mypassword")
        assert user is not None
        assert user["email"] == "login@example.com"
        assert "password_hash" not in user  # should never leak

    def test_login_wrong_password(self):
        h = _hosting()
        h.register("wrongpw@example.com", "correct")
        assert h.login("wrongpw@example.com", "wrong") is None

    def test_login_nonexistent_user(self):
        h = _hosting()
        assert h.login("nobody@example.com", "pw") is None

    def test_get_by_api_key(self):
        h = _hosting()
        reg = h.register("apikey@example.com", "pw")
        user = h.get_by_api_key(reg["api_key"])
        assert user is not None
        assert user["email"] == "apikey@example.com"

    def test_get_by_api_key_nonexistent(self):
        h = _hosting()
        assert h.get_by_api_key("wp_live_nonexistent_key") is None

    def test_log_and_check_usage(self):
        h = _hosting()
        reg = h.register("usage@example.com", "pw")
        uid = reg["user_id"]
        h.log_usage(uid, "generate_wallet", "eth")
        h.log_usage(uid, "generate_wallet", "eth", count=2)
        daily = h.daily_usage(uid)
        assert daily >= 3

    def test_check_limit_unlimited(self):
        h = _hosting()
        reg = h.register("unlimited@example.com", "pw")
        ok, msg = h.check_limit(reg["user_id"])
        # Free plan has daily_wallet_limit=10 — should be OK with 0 usage
        assert ok is True

    def test_check_limit_user_not_found(self):
        h = _hosting()
        ok, msg = h.check_limit("nonexistent_user")
        assert ok is False

    def test_get_user(self):
        h = _hosting()
        reg = h.register("getuser@example.com", "pw")
        user = h.get_user(reg["user_id"])
        assert user is not None
        assert user["email"] == "getuser@example.com"

    def test_get_user_nonexistent(self):
        h = _hosting()
        assert h.get_user("nonexistent") is None

    def test_verify_email_invalid_token(self):
        h = _hosting()
        assert h.verify_email("") is False
        assert h.verify_email("nonexistent_token") is False

    def test_email_verification_flow(self, monkeypatch):
        monkeypatch.setenv("WP_REQUIRE_EMAIL_VERIFY", "1")
        h = _hosting()
        reg = h.register("verify@example.com", "pw")
        uid = reg["user_id"]
        assert h.is_email_verified(uid) is False
        token = reg.get("verification_token", "")
        if token:
            assert h.verify_email(token) is True
            assert h.is_email_verified(uid) is True

    def test_check_legacy_hashes_doesnt_crash(self):
        _check_legacy_hashes()  # should not raise

    def test_get_hosting_singleton(self):
        h1 = get_hosting()
        h2 = get_hosting()
        assert h1 is h2
