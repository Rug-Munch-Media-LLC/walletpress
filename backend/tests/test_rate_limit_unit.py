"""Tests: token bucket rate limiter."""

import os
import time

os.environ["WP_VAULT_PASSWORD"] = "test-pw-rate"
os.environ["WP_DATA_DIR"] = "/tmp/wp_test_rate"

from core.rate_limit import TokenBucket, RateLimitMiddleware


class TestTokenBucket:
    def test_consume_when_available(self):
        bucket = TokenBucket(rate=10, per_seconds=60)
        allowed, remaining, _ = bucket.consume()
        assert allowed is True
        assert remaining == 9.0  # one consumed

    def test_consume_exhaustion(self):
        bucket = TokenBucket(rate=3, per_seconds=60)
        for _ in range(3):
            allowed, _, _ = bucket.consume()
            assert allowed is True
        allowed, remaining, reset_in = bucket.consume()
        assert allowed is False
        assert remaining < 0.001  # near-zero tolerance for time.monotonic() drift
        assert reset_in > 0

    def test_token_refill_over_time(self):
        bucket = TokenBucket(rate=60, per_seconds=60)
        # Use all tokens
        for _ in range(60):
            bucket.consume()
        allowed, _, _ = bucket.consume()
        assert allowed is False

        # Simulate 1 second passing — should get 1 token back
        bucket.last_refill = time.monotonic() - 1.0
        allowed, remaining, _ = bucket.consume()
        assert allowed is True
        assert remaining < 1.0  # partial remaining after consuming the refilled token

    def test_custom_rate_and_period(self):
        bucket = TokenBucket(rate=100, per_seconds=10)
        for _ in range(100):
            allowed, _, _ = bucket.consume()
            assert allowed is True
        allowed, _, _ = bucket.consume()
        assert allowed is False

    def test_initial_tokens_at_rate(self):
        bucket = TokenBucket(rate=5, per_seconds=30)
        assert bucket.tokens == 5.0


class TestRateLimitMiddleware:
    def test_get_key_from_api_key_header(self):
        mw = RateLimitMiddleware(None)
        req = _make_request(headers={"X-API-Key": "wp_test_key_12345"})
        key = mw._get_key(req)
        assert key.startswith("key:")

    def test_get_key_fallback_to_ip(self):
        mw = RateLimitMiddleware(None)
        req = _make_request(headers={}, client_host="10.0.0.1")
        key = mw._get_key(req)
        assert key == "ip:10.0.0.1"

    def test_get_key_from_authorization(self):
        mw = RateLimitMiddleware(None)
        req = _make_request(headers={"Authorization": "Bearer wp_test_bearer_key"})
        key = mw._get_key(req)
        assert key.startswith("key:")

    def test_stats_structure(self):
        mw = RateLimitMiddleware(None, rate=30, per_seconds=60)
        stats = mw.stats()
        assert "total_buckets" in stats
        assert "active_in_last_5min" in stats
        assert "rate_per_minute" in stats
        assert stats["rate_per_minute"] == 30


def _make_request(headers=None, client_host="127.0.0.1"):
    """Build a minimal request-like object for _get_key testing."""

    class MockClient:
        host = client_host

    class MockRequest:
        def __init__(self):
            self.headers = headers or {}
            self.client = MockClient() if client_host else None
            self.url = type("URL", (), {"path": "/test"})()

    return MockRequest()
