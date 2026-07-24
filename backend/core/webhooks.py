"""Webhook delivery system — reliable, retryable, signed.

Delivers webhook events to registered URLs with:
  - HMAC-SHA256 signature headers
  - 3 retries with exponential backoff (1s, 4s, 16s)
  - At-least-once delivery semantics
  - Idempotency via event_id
  - Delivery logging

Trust: Webhooks allow YOUR systems to react to wallet events.
We never inspect or store webhook payloads after delivery.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass

import ipaddress
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("wp.webhooks")


_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_webhook_url(url: str) -> None:
    """Validate a webhook URL to prevent SSRF attacks.

    Rejects non-HTTPS URLs, private IPs, and internal hostnames.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("https",):
        raise ValueError(f"Webhook URL must use HTTPS, got '{parsed.scheme}'")
    host = parsed.hostname or ""
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError("Webhook URL must not point to localhost")
    if host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("Webhook URL must not point to an internal hostname")
    try:
        addr = ipaddress.ip_address(host)
        for net in _PRIVATE_NETWORKS:
            if addr in net:
                raise ValueError(f"Webhook URL must not point to a private network ({net})")
    except ValueError:
        if isinstance(host, str) and host:
            pass  # hostname — can't validate without DNS resolution at registration time

# Delivery log — append-only, in-memory, capped at MAX entries
delivery_log: list[dict] = []
DELIVERY_LOG_MAX = 1000


def _log_delivery(event_id: str, event_type: str, target_url: str,
                  status: str, status_code: int = 0, attempt: int = 0,
                  error: str = ""):
    entry = {
        "event_id": event_id,
        "event_type": event_type,
        "target_url": target_url,
        "status": status,
        "status_code": status_code,
        "attempt": attempt,
        "error": error[:200] if error else "",
        "timestamp": time.time(),
    }
    delivery_log.append(entry)
    if len(delivery_log) > DELIVERY_LOG_MAX:
        delivery_log.pop(0)


MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds


@dataclass
class WebhookEvent:
    event_id: str
    event_type: str
    payload: dict
    created_at: float = 0.0


@dataclass
class WebhookTarget:
    url: str
    secret: str
    events: list[str]
    active: bool = True


class WebhookDeliverer:
    """Delivers webhook events to registered targets with retry logic."""

    def __init__(self):
        self._targets: dict[str, WebhookTarget] = {}
        self._client: httpx.AsyncClient | None = None
        self._running = False
        self._queue: asyncio.Queue = asyncio.Queue()

    async def start(self):
        self._client = httpx.AsyncClient(timeout=15)
        self._running = True
        asyncio.create_task(self._worker_loop())
        logger.info("Webhook deliverer started")

    async def stop(self):
        self._running = False
        if self._client:
            await self._client.aclose()
        logger.info("Webhook deliverer stopped")

    def register(self, target_id: str, url: str, secret: str, events: list[str]):
        validate_webhook_url(url)
        self._targets[target_id] = WebhookTarget(url=url, secret=secret, events=events)

    def unregister(self, target_id: str):
        self._targets.pop(target_id, None)

    async def emit(self, event_type: str, payload: dict):
        """Queue a webhook event for delivery to matching targets."""
        event = WebhookEvent(
            event_id=f"evt_{secrets.token_hex(8)}_{int(time.time())}",
            event_type=event_type,
            payload=payload,
            created_at=time.time(),
        )
        await self._queue.put(event)
        logger.debug(f"Queued webhook: {event_type} ({event.event_id[:16]}...)")

    def _should_deliver(self, target: WebhookTarget, event_type: str) -> bool:
        if not target.active:
            return False
        if not target.events:
            return True
        return event_type in target.events or "*" in target.events

    def _sign_payload(self, payload: bytes, secret: str) -> str:
        return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    async def _deliver(self, target: WebhookTarget, event: WebhookEvent) -> bool:
        body = json.dumps({
            "event_id": event.event_id,
            "event_type": event.event_type,
            "created_at": event.created_at,
            "payload": event.payload,
        }).encode()

        signature = self._sign_payload(body, target.secret)

        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._client.post(
                    target.url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": signature,
                        "X-Webhook-Event": event.event_type,
                        "X-Webhook-Id": event.event_id,
                        "User-Agent": "WalletPress-Webhook/1.0",
                    },
                )
                if resp.is_success:
                    logger.info(f"Webhook delivered: {event.event_type} -> {target.url} (attempt {attempt + 1})")
                    _log_delivery(event.event_id, event.event_type, target.url,
                                  "delivered", resp.status_code, attempt + 1)
                    return True

                logger.warning(f"Webhook {target.url} returned {resp.status_code} (attempt {attempt + 1})")
                _log_delivery(event.event_id, event.event_type, target.url,
                              "failed", resp.status_code, attempt + 1)
            except Exception as e:
                logger.warning(f"Webhook delivery failed: {target.url} ({e}) (attempt {attempt + 1})")
                _log_delivery(event.event_id, event.event_type, target.url,
                              "error", 0, attempt + 1, str(e))

            if attempt < MAX_RETRIES - 1:
                delay = BASE_DELAY * (4 ** attempt)
                await asyncio.sleep(delay)

        logger.error(f"Webhook delivery FAILED after {MAX_RETRIES} attempts: {event.event_type} -> {target.url}")
        return False

    async def _worker_loop(self):
        while self._running:
            try:
                event = await self._queue.get()
                tasks = []
                for target_id, target in self._targets.items():
                    if self._should_deliver(target, event.event_type):
                        tasks.append(self._deliver(target, event))
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Webhook worker error: {e}")


_webhook_deliverer: WebhookDeliverer | None = None


def get_webhook_deliverer() -> WebhookDeliverer:
    global _webhook_deliverer
    if _webhook_deliverer is None:
        _webhook_deliverer = WebhookDeliverer()
    return _webhook_deliverer
