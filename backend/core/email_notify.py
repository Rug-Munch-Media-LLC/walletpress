"""Email notification system for wallet events.

Sends transactional emails via SMTP for:
  - Wallet generated (confirmation with address)
  - Payment received (amount + tx hash)
  - Low balance alert (wallet below threshold)
  - Rotation due (wallet scheduled for rotation)
  - Security alert (suspicious activity detected)

Trust: Email credentials are stored in env vars, never logged.
All email sending is async and non-blocking.
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("wp.email")

SMTP_HOST = os.getenv("WP_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("WP_SMTP_PORT", "587"))
SMTP_USER = os.getenv("WP_SMTP_USER", "")
SMTP_PASS = os.getenv("WP_SMTP_PASS", "")
FROM_EMAIL = os.getenv("WP_FROM_EMAIL", "walletpress@localhost")
TO_EMAIL = os.getenv("WP_NOTIFY_EMAIL", "")


@dataclass
class EmailMessage:
    subject: str
    body_text: str
    body_html: str = ""


TEMPLATES = {
    "wallet.generated": {
        "subject": "WalletPress — Wallet Generated: {chain}",
        "body": """Wallet Generated

Chain: {chain}
Address: {address}
Label: {label}
Time: {time}

This wallet is stored in your encrypted vault.
Use GET /vault/{{id}} with your API key to retrieve the private key.

---
WalletPress — Self-Hosted Multi-Chain Wallet Generator
""",
    },
    "payment.received": {
        "subject": "WalletPress — Payment Received: ${amount}",
        "body": """Payment Received

Amount: ${amount}
Token: {token}
Chain: {chain}
From: {from_address}
TX: {tx_hash}
Time: {time}

---
WalletPress
""",
    },
    "balance.alert": {
        "subject": "WalletPress — Low Balance Alert: {wallet_id}",
        "body": """Low Balance Alert

Wallet: {wallet_id}
Chain: {chain}
Address: {address}
Current Balance: ${balance_usd}
Threshold: ${threshold}
Time: {time}

Action recommended: Fund this wallet or rotate to a new one.

---
WalletPress
""",
    },
    "rotation.due": {
        "subject": "WalletPress — Rotation Due: {wallet_id}",
        "body": """Wallet Rotation Due

Wallet: {wallet_id}
Chain: {chain}
Address: {address}
Rotation Due: {due_date}

Rotate this wallet to maintain security best practices.

---
WalletPress
""",
    },
    "security.alert": {
        "subject": "WalletPress — Security Alert: {event}",
        "body": """Security Alert

Event: {event}
Wallet: {wallet_id}
Time: {time}
Details: {details}

Review your vault access immediately if this was unexpected.

---
WalletPress
""",
    },
}


class EmailNotifier:
    """Async email notification sender via SMTP."""

    def __init__(self):
        self._enabled = bool(SMTP_HOST and SMTP_USER and SMTP_PASS and TO_EMAIL)

    async def send_event(self, event_type: str, data: dict) -> bool:
        """Send a notification email for a wallet event.

        Args:
            event_type: One of wallet.generated, payment.received, etc.
            data: Template variables (chain, address, amount, etc.)

        Returns:
            True if email was sent successfully.
        """
        if not self._enabled:
            logger.debug(f"Email not configured, skipping {event_type}")
            return False

        template = TEMPLATES.get(event_type)
        if not template:
            logger.warning(f"No email template for {event_type}")
            return False

        subject = template["subject"].format(**data)
        body = template["body"].format(**data)

        return await self._send(subject, body)

    async def _send(self, subject: str, body: str) -> bool:
        """Send email via SMTP in executor to avoid blocking."""
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._send_sync, subject, body)
            logger.info(f"Email sent: {subject[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False

    def _send_sync(self, subject: str, body: str):
        """Synchronous SMTP send (runs in thread pool)."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = TO_EMAIL
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(f"<pre style='font:14px/1.5 monospace'>{body}</pre>", "html", "utf-8"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls(context=ctx)
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())


_notifier: EmailNotifier | None = None


def get_notifier() -> EmailNotifier:
    global _notifier
    if _notifier is None:
        _notifier = EmailNotifier()
    return _notifier
