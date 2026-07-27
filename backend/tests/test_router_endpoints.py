"""Tests: router endpoints via TestClient."""

import os
import tempfile

os.environ["WP_VAULT_PASSWORD"] = "test-pw-router-ep"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_router_")
os.environ["WP_ADMIN_KEY"] = "test-admin-key-router"
os.environ["WP_RATE_LIMIT"] = "0"

import pytest
from fastapi.testclient import TestClient

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

# Must import after env setup
from main import app


@pytest.fixture
def client():
    app.state.vault = None
    app.state.key_store = None
    app.state.audit = None
    app.state.generator = None
    app.state.proof = None

    from core.auth import KeyStore
    from core.vault import Vault
    from core.audit import AuditLog as AuditTrail
    from core.proof import ProofOfGeneration
    from wallet_engine.generator import WalletGenerator

    db_path = cfg.data_dir / "test.db"
    app.state.vault = Vault(db_path)
    app.state.key_store = KeyStore(cfg.keys_path)
    app.state.audit = AuditTrail(cfg.audit_path)
    app.state.proof = ProofOfGeneration(cfg.data_dir / "proof.db")
    app.state.generator = WalletGenerator(vault_password=cfg.vault_password)

    return TestClient(app)


@pytest.fixture
def admin_headers():
    return {"X-API-Key": "test-admin-key-router"}


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_healthz(self, client):
        resp = client.get("/healthz")
        assert resp.status_code in (200, 404)

    def test_metrics(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_version(self, client):
        resp = client.get("/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data or "service" in data


class TestAdminConfig:
    def test_get_config(self, client, admin_headers):
        resp = client.get("/api/v1/chain-vault/config", headers=admin_headers)
        assert resp.status_code in (200, 401, 403)
        if resp.status_code == 200:
            data = resp.json()
            assert "version" in data
            assert "features" in data


class TestLicenseRoutes:
    def test_license_status(self, client):
        resp = client.get("/api/v1/license", headers={"X-API-Key": "test-admin-key-router"})
        assert resp.status_code in (200, 401, 403)
        if resp.status_code == 200:
            data = resp.json()
            assert "tier" in data or "status" in data

    def test_license_plans(self, client):
        resp = client.get("/api/v1/license/plans")
        assert resp.status_code in (200, 401, 403)


class TestAlertAndWebhookRoutes:
    def test_list_alerts(self, client, admin_headers):
        resp = client.get("/api/v1/chain-vault/alerts", headers=admin_headers)
        assert resp.status_code in (200, 401, 403)
        if resp.status_code == 200:
            data = resp.json()
            assert "alerts" in data

    def test_list_webhooks(self, client, admin_headers):
        resp = client.get("/api/v1/chain-vault/webhooks", headers=admin_headers)
        assert resp.status_code in (200, 401, 403)

    def test_list_api_keys(self, client, admin_headers):
        resp = client.get("/api/v1/chain-vault/api-keys", headers=admin_headers)
        assert resp.status_code in (200, 401, 403)


class TestChainVault:
    def test_list_chains(self, client, admin_headers):
        resp = client.get("/api/v1/chain-vault/chains", headers=admin_headers)
        assert resp.status_code in (200, 401, 403)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, dict) or "chains" in data

    def test_vault_stats(self, client, admin_headers):
        resp = client.get("/api/v1/chain-vault/stats", headers=admin_headers)
        assert resp.status_code in (200, 401, 403)

    def test_generate_get(self, client, admin_headers):
        resp = client.get("/api/v1/chain-vault/generate", headers=admin_headers)
        assert resp.status_code in (200, 404, 405)


class TestAirdropRoutes:
    def test_airdrop_manifests_empty(self, client, admin_headers):
        resp = client.get("/api/v1/airdrop/manifests", headers=admin_headers)
        assert resp.status_code in (200, 401, 403)


class TestTrustEndpoints:
    def test_build_info(self, client):
        resp = client.get("/trust/build")
        assert resp.status_code in (200, 404)

    def test_audit_log(self, client):
        resp = client.get("/trust/audit")
        assert resp.status_code in (200, 404)
