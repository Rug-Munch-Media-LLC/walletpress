"""Tests: arweave, onboarding, proof_digest, dependencies, and import verification for other core modules."""

import os
import tempfile
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-more-core"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_more_")
os.environ["WP_RATE_LIMIT"] = "0"

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

# ── Arweave tests ────────────────────────────────────────────────


def test_arweave_commit_no_wallet():
    """Without AR wallet configured, should return pending_tx."""
    from core.arweave import commit_root

    result = commit_root("0xabc123", 42)
    assert result["committed"] is False
    assert "pending_tx" in result
    assert result["pending_tx"]["root_hash"] == "0xabc123"
    assert result["pending_tx"]["leaf_count"] == 42


def test_arweave_build_unsigned_tx():
    from core.arweave import _build_unsigned_tx

    result = _build_unsigned_tx("0xdef", 10, "v1")
    assert result["protocol"] == "v1"
    assert result["root_hash"] == "0xdef"
    assert result["leaf_count"] == 10
    assert "submission_url" in result
    assert "cli_command" in result


# ── Dependencies tests ────────────────────────────────────────────


def test_dependencies_imports():
    """All dependency functions should be importable."""
    from core.dependencies import (
        get_vault,
        get_generator,
        get_key_store,
        get_audit,
        get_license,
        get_proof,
    )

    assert callable(get_vault)
    assert callable(get_generator)
    assert callable(get_key_store)
    assert callable(get_audit)
    assert callable(get_license)
    assert callable(get_proof)


# ── Onboarding tests ──────────────────────────────────────────────


def test_onboarding_has_functions():
    import core.onboarding

    assert hasattr(core.onboarding, "onboarding_status")


# ── Proof digest tests ────────────────────────────────────────────


def test_proof_digest_basic():
    from core.proof_digest import create_digest, verify_wallet, generate_verification_page

    result = create_digest()
    assert "committed" in result or "leaf_count" in result
    vresult = verify_wallet("nonexistent", "0xabc", "0xpub")
    assert isinstance(vresult, dict)
    html = generate_verification_page("0xtest")
    assert "<!DOCTYPE html>" in html
    assert "0xtest" in html


# ── Rate limit tests ──────────────────────────────────────────────


def test_rate_limit_imports():
    import core.rate_limit

    assert hasattr(core.rate_limit, "TokenBucket") or hasattr(
        core.rate_limit, "RateLimitMiddleware"
    )


# ── License check tests ───────────────────────────────────────────


def test_license_check_imports():
    import core.license_check

    assert core.license_check.__name__ == "core.license_check"


# ── JWT auth tests ────────────────────────────────────────────────


def test_jwt_auth_imports():
    import core.jwt_auth

    assert hasattr(core.jwt_auth, "validate_rmi_jwt") or hasattr(
        core.jwt_auth, "JWTValidationMiddleware"
    )


# ── Webhooks tests ────────────────────────────────────────────────


def test_webhooks_imports():
    import core.webhooks

    assert hasattr(core.webhooks, "WebhookDeliverer") or hasattr(core.webhooks, "WebhookEvent")


# ── TOTP tests ────────────────────────────────────────────────────


def test_totp_imports():
    import core.totp

    assert hasattr(core.totp, "TOTPManager") or hasattr(core.totp, "generate_totp")


# ── PDF tests ─────────────────────────────────────────────────────


def test_pdf_imports():
    import core.pdf

    assert hasattr(core.pdf, "PaperWalletPDF") or hasattr(core.pdf, "generate_paper_wallet")


# ── Hosting tests ─────────────────────────────────────────────────


def test_hosting_imports():
    import core.hosting

    assert hasattr(core.hosting, "HostingDB") or hasattr(core.hosting, "PLANS")


# ── agent_safety tests ────────────────────────────────────────────


def test_agent_safety_imports():
    import core.agent_safety

    assert hasattr(core.agent_safety, "check_action_allowed") or hasattr(
        core.agent_safety, "kill_agent"
    )
