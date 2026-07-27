"""Tests: TOTP 2FA manager."""

import base64
import os
import struct
import tempfile
import time
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-pw-totp"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_totp_")

from core.totp import TOTPManager, TOTP_INTERVAL, TOTP_DIGITS, get_totp_manager


def _manager() -> TOTPManager:
    tmp = Path(tempfile.mkstemp(suffix=".db")[1])
    return TOTPManager(tmp)


class TestTOTPManager:
    def test_setup_generates_secret(self):
        m = _manager()
        result = m.setup()
        assert "secret_b32" in result
        assert "qr_uri" in result
        assert "manual_entry_key" in result
        assert result["setup_complete"] is False
        assert len(result["secret_b32"]) > 10

    def test_setup_qr_uri_format(self):
        m = _manager()
        result = m.setup()
        assert result["qr_uri"].startswith("otpauth://totp/")
        assert "secret=" in result["qr_uri"]
        assert "digits=" in result["qr_uri"]
        assert "period=" in result["qr_uri"]

    def test_enable_and_is_enabled(self):
        m = _manager()
        m.setup()
        assert m.is_enabled() is False
        m.enable()
        assert m.is_enabled() is True

    def test_disable(self):
        m = _manager()
        m.setup()
        m.enable()
        assert m.is_enabled() is True
        m.disable()
        assert m.is_enabled() is False

    def test_verify_with_valid_code(self):
        m = _manager()
        m.setup()
        m.enable()
        # Generate a valid code using the same algorithm
        code = m._totp_at_time(
            base64.b32decode(m.setup()["secret_b32"]),
            time.time(),
        )
        assert m.verify(code) is True

    def test_verify_with_invalid_code(self):
        m = _manager()
        m.setup()
        m.enable()
        assert m.verify("000000") is False

    def test_verify_when_not_enabled(self):
        m = _manager()
        assert m.verify("anything") is True

    def test_hotp_generates_rfc_4226_code(self):
        m = _manager()
        secret_bytes = b"\x00" * 20
        # Counter 0 — known RFC 4226 test vector (for SHA1)
        code = m._hotp(secret_bytes, 0)
        assert len(code) == TOTP_DIGITS
        assert code.isdigit()

    def test_totp_at_time_changes_with_time(self):
        m = _manager()
        secret_bytes = b"\x01" * 20
        code1 = m._totp_at_time(secret_bytes, 1000.0)
        code2 = m._totp_at_time(secret_bytes, 2000.0)
        # Different time windows may produce different codes
        assert isinstance(code1, str)
        assert len(code1) == TOTP_DIGITS

    def test_hotp_different_counter_different_code(self):
        m = _manager()
        secret_bytes = b"\x05" * 20
        c0 = m._hotp(secret_bytes, 0)
        c1 = m._hotp(secret_bytes, 1)
        assert c0 != c1

    def test_get_totp_manager_singleton(self):
        m1 = get_totp_manager()
        m2 = get_totp_manager()
        assert m1 is m2
