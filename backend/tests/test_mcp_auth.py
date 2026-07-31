"""Tests: /mcp admin-key authentication gate.

Regression tests for the unauthenticated MCP wallet-drain vulnerability:
the AI Wallet Agent MCP server (/mcp) can decrypt keys, sweep wallets, and
broadcast transactions, and was previously exempt from authentication
(require_auth_on_mutations skipped /mcp/). All /mcp routes now require
WP_ADMIN_KEY via X-Admin-Key, Authorization: Bearer, or X-API-Key headers.
"""

import pytest

# conftest.py sets WP_ADMIN_KEY=test-admin-key-12345
ADMIN_KEY = "test-admin-key-12345"


def _mcp_payload():
    return {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}


@pytest.fixture(autouse=True)
def _pin_admin_key_env():
    """Pin WP_ADMIN_KEY for this module's tests.

    test_router_endpoints.py sets WP_ADMIN_KEY to a different value at module
    import time, and pytest imports ALL test modules during collection (before
    any test runs). The JWT validation middleware reads WP_ADMIN_KEY at
    request time, so the Bearer bypass would otherwise see the wrong value and
    reject a valid admin-key Bearer token. Restore the previous value after
    each test to avoid leaking into other modules.
    """
    import os

    prev = os.environ.get("WP_ADMIN_KEY")
    os.environ["WP_ADMIN_KEY"] = ADMIN_KEY
    yield
    if prev is None:
        os.environ.pop("WP_ADMIN_KEY", None)
    else:
        os.environ["WP_ADMIN_KEY"] = prev


# ── Unauthenticated requests MUST be rejected ──────────────────────────────


def test_post_mcp_messages_without_auth_rejected(client):
    r = client.post("/mcp/messages", json=_mcp_payload())
    assert r.status_code == 401
    assert r.json()["code"] == "mcp_unauthorized"


def test_post_mcp_messages_slash_without_auth_rejected(client):
    r = client.post("/mcp/messages/", json=_mcp_payload())
    assert r.status_code == 401


def test_get_mcp_sse_without_auth_rejected(client):
    # Unauthenticated SSE must be rejected before the stream is established.
    r = client.get("/mcp/sse")
    assert r.status_code == 401
    assert r.json()["code"] == "mcp_unauthorized"


def test_post_mcp_messages_wrong_key_rejected(client):
    r = client.post("/mcp/messages", json=_mcp_payload(), headers={"X-Admin-Key": "wrong-key"})
    assert r.status_code == 401


def test_get_mcp_sse_wrong_key_rejected(client):
    r = client.get("/mcp/sse", headers={"X-Admin-Key": "wrong-key"})
    assert r.status_code == 401


def test_post_mcp_messages_empty_key_rejected(client):
    r = client.post("/mcp/messages", json=_mcp_payload(), headers={"X-Admin-Key": ""})
    assert r.status_code == 401


# ── Authenticated requests MUST pass the gate ──────────────────────────────


def test_post_mcp_messages_valid_admin_key_passes_gate(client):
    # A valid key passes auth; the MCP app then requires session_id (400).
    # This proves the request reached the MCP server instead of being 401'd.
    r = client.post(
        "/mcp/messages/",
        json=_mcp_payload(),
        headers={"X-Admin-Key": ADMIN_KEY, "Host": "localhost:8010"},
    )
    assert r.status_code == 400
    assert "session_id" in r.text.lower()


def test_post_mcp_messages_valid_bearer_passes_gate(client):
    r = client.post(
        "/mcp/messages/",
        json=_mcp_payload(),
        headers={"Authorization": f"Bearer {ADMIN_KEY}", "Host": "localhost:8010"},
    )
    assert r.status_code == 400


def test_post_mcp_messages_valid_api_key_header_passes_gate(client):
    r = client.post(
        "/mcp/messages/",
        json=_mcp_payload(),
        headers={"X-API-Key": ADMIN_KEY, "Host": "localhost:8010"},
    )
    assert r.status_code == 400


# ── Other routes are unaffected ────────────────────────────────────────────


def test_health_public(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_x402_marketplace_still_mounted(client):
    # The root-mounted x402 app must still be reachable (mount reorder).
    r = client.get("/api/v1/marketplace/pricing")
    assert r.status_code == 200


def test_mcp_does_not_break_normal_api_auth(client):
    # Normal API write routes still enforce the standard key + role flow.
    r = client.post(
        "/api/v1/team/keys",
        params={"label": "t", "role": "operator"},
        headers={"X-API-Key": ADMIN_KEY},
    )
    assert r.status_code == 200


def test_mcp_does_not_exempt_other_routes(client):
    r = client.post("/api/v1/team/keys", params={"label": "t", "role": "operator"})
    assert r.status_code == 401
