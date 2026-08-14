"""Tests: email notifier and FastAPI dependencies."""

import os
import tempfile

os.environ["WP_VAULT_PASSWORD"] = "test-pw-email-deps"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_email_")

import pytest

from core.dependencies import get_generator, get_vault
from core.email_notify import TEMPLATES, EmailMessage, EmailNotifier, get_notifier


class TestEmailNotifier:
    def test_notifier_init_disabled(self):
        n = EmailNotifier()
        assert n._enabled is False

    @pytest.mark.asyncio
    async def test_send_event_disabled_returns_false(self):
        n = EmailNotifier()
        result = await n.send_event("wallet.generated", {"chain": "eth", "address": "0x1"})
        assert result is False

    def test_templates_defined(self):
        assert "wallet.generated" in TEMPLATES
        assert "payment.received" in TEMPLATES
        assert "balance.alert" in TEMPLATES
        assert "rotation.due" in TEMPLATES
        assert "security.alert" in TEMPLATES

    def test_templates_format_subject(self):
        tmpl = TEMPLATES["wallet.generated"]
        subject = tmpl["subject"].format(chain="ETH")
        body = tmpl["body"].format(chain="ETH", address="0xabc", label="test", time="now")
        assert "ETH" in subject
        assert "0xabc" in body

    def test_templates_format_payment(self):
        tmpl = TEMPLATES["payment.received"]
        subject = tmpl["subject"].format(amount="100")
        body = tmpl["body"].format(
            amount="100",
            token="USDC",
            chain="eth",
            from_address="0xsender",
            tx_hash="0xtx",
            time="now",
        )
        assert "100" in subject
        assert "USDC" in body
        assert "0xsender" in body

    def test_templates_format_security_alert(self):
        tmpl = TEMPLATES["security.alert"]
        body = tmpl["body"].format(
            event="suspicious_login", wallet_id="w1", time="now", details="new IP"
        )
        assert "suspicious_login" in body
        assert "w1" in body

    @pytest.mark.asyncio
    async def test_send_event_unknown_type_returns_false(self):
        n = EmailNotifier()
        result = await n.send_event("unknown.event.type", {})
        assert result is False

    def test_get_notifier_singleton(self):
        n1 = get_notifier()
        n2 = get_notifier()
        assert n1 is n2

    def test_email_message_dataclass(self):
        msg = EmailMessage(subject="Test", body_text="Hello")
        assert msg.subject == "Test"
        assert msg.body_text == "Hello"
        assert msg.body_html == ""


class TestDependencies:
    @pytest.mark.asyncio
    async def test_get_vault_no_app_state(self):
        class MockState:
            vault = None

        class MockApp:
            state = MockState()

        class MockRequest:
            app = MockApp()

        vault = await get_vault(MockRequest())
        assert vault is not None

    @pytest.mark.asyncio
    async def test_get_vault_with_existing_state(self):
        class MockState:
            vault = "already_set"

        class MockApp:
            state = MockState()

        class MockRequest:
            app = MockApp()

        vault = await get_vault(MockRequest())
        assert vault == "already_set"

    @pytest.mark.asyncio
    async def test_get_generator_no_state(self):
        class MockState:
            generator = None

        class MockApp:
            state = MockState()

        class MockRequest:
            app = MockApp()

        gen = await get_generator(MockRequest())
        assert gen is not None
