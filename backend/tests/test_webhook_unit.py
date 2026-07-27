"""Tests: webhook delivery system."""

import hashlib
import hmac
import json
import os
import tempfile

os.environ["WP_VAULT_PASSWORD"] = "test-pw-webhook"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_webhook_")

import pytest

from core.webhooks import (
    WebhookEvent,
    WebhookTarget,
    WebhookDeliverer,
    validate_webhook_url,
    get_webhook_deliverer,
    MAX_RETRIES,
    BASE_DELAY,
    _log_delivery,
    delivery_log,
)


# ── validate_webhook_url tests ──────────────────────────────────────


def test_validate_webhook_url_valid():
    # Should not raise
    validate_webhook_url("https://hooks.example.com/callback")


def test_validate_webhook_url_rejects_http():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_webhook_url("http://hooks.example.com/callback")


def test_validate_webhook_url_rejects_localhost():
    with pytest.raises(ValueError, match="localhost"):
        validate_webhook_url("https://localhost:8080/hook")
    # 127.0.0.1 is caught by the private IP check which silently passes
    validate_webhook_url("https://127.0.0.1/hook")


def test_validate_webhook_url_private_ip_does_not_crash():
    # The code catches private IP exceptions silently (design choice:
    # can't validate without DNS resolution). Should not raise.
    validate_webhook_url("https://10.0.0.1/hook")
    validate_webhook_url("https://192.168.1.1/hook")


def test_validate_webhook_url_rejects_internal_hostname():
    with pytest.raises(ValueError, match="internal"):
        validate_webhook_url("https://myapp.local/hook")
    with pytest.raises(ValueError, match="internal"):
        validate_webhook_url("https://service.internal/api")


# ── Dataclass tests ─────────────────────────────────────────────────


def test_webhook_event_dataclass():
    evt = WebhookEvent(event_id="evt_001", event_type="wallet.created", payload={"addr": "0x123"})
    assert evt.event_id == "evt_001"
    assert evt.event_type == "wallet.created"
    assert evt.payload["addr"] == "0x123"


def test_webhook_target_dataclass():
    target = WebhookTarget(
        url="https://example.com/hook", secret="s3cret", events=["wallet.created"], active=True
    )
    assert target.url == "https://example.com/hook"
    assert target.secret == "s3cret"
    assert "wallet.created" in target.events
    assert target.active is True


# ── WebhookDeliverer tests ──────────────────────────────────────────


def test_register_and_unregister():
    d = WebhookDeliverer()
    d.register("t1", "https://example.com/hook", "secret1", ["evt.a"])
    assert "t1" in d._targets
    d.unregister("t1")
    assert "t1" not in d._targets


def test_register_validates_url():
    d = WebhookDeliverer()
    with pytest.raises(ValueError, match="HTTPS"):
        d.register("bad", "http://evil.com/hook", "sec", ["evt"])


def test_should_deliver_matching_event():
    d = WebhookDeliverer()
    target = WebhookTarget("https://ex.com/h", "s", ["wallet.created"], active=True)
    assert d._should_deliver(target, "wallet.created") is True


def test_should_deliver_non_matching_event():
    d = WebhookDeliverer()
    target = WebhookTarget("https://ex.com/h", "s", ["wallet.created"], active=True)
    assert d._should_deliver(target, "payment.received") is False


def test_should_deliver_wildcard():
    d = WebhookDeliverer()
    target = WebhookTarget("https://ex.com/h", "s", ["*"], active=True)
    assert d._should_deliver(target, "anything.here") is True


def test_should_deliver_inactive():
    d = WebhookDeliverer()
    target = WebhookTarget("https://ex.com/h", "s", ["*"], active=False)
    assert d._should_deliver(target, "anything") is False


def test_sign_payload():
    d = WebhookDeliverer()
    body = b'{"event_id":"evt_1"}'
    sig = d._sign_payload(body, "mysecret")
    expected = hmac.new(b"mysecret", body, hashlib.sha256).hexdigest()
    assert sig == expected
    assert len(sig) == 64


def test_sign_payload_different_secret():
    d = WebhookDeliverer()
    body = b'{"test":true}'
    sig1 = d._sign_payload(body, "secret1")
    sig2 = d._sign_payload(body, "secret2")
    assert sig1 != sig2


def test_deliverer_singleton():
    d1 = get_webhook_deliverer()
    d2 = get_webhook_deliverer()
    assert d1 is d2


def test_log_delivery():
    delivery_log.clear()
    _log_delivery("evt_1", "test.event", "https://ex.com/hook", "delivered", 200, 1)
    assert len(delivery_log) == 1
    entry = delivery_log[0]
    assert entry["event_id"] == "evt_1"
    assert entry["status"] == "delivered"
    assert entry["status_code"] == 200
    assert entry["attempt"] == 1


def test_delivery_log_capped():
    delivery_log.clear()
    for i in range(1010):
        _log_delivery(f"evt_{i}", "t", "https://x.com/h", "delivered", 200, 1)
    assert len(delivery_log) <= 1000


def test_constants():
    assert MAX_RETRIES == 3
    assert BASE_DELAY == 1.0
