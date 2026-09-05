import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ["WP_VAULT_PASSWORD"] = "test-vault-password-1234567890"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_")
os.environ["WP_ADMIN_KEY"] = "test-admin-key-12345"
os.environ["WP_RATE_LIMIT"] = "0"

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]


@pytest.fixture
def client():
    from main import app

    app.state.vault = None
    app.state.key_store = None
    app.state.audit = None
    app.state.generator = None
    app.state.proof = None

    from core.audit import AuditLog as AuditTrail
    from core.auth import KeyStore
    from core.proof import ProofOfGeneration
    from core.vault import Vault
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
    return {"X-API-Key": "test-admin-key-12345"}
