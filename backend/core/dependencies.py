"""FastAPI dependencies for wallet services.

Enables testability via dependency_overrides — tests can inject mock
vaults, generators, etc. without monkey-patching module-level globals.
"""

from __future__ import annotations


from fastapi import Request

from core.config import cfg


async def get_vault(request: Request):
    """Get vault instance from app state (or create if first call)."""
    app = request.app
    if not hasattr(app.state, "vault") or app.state.vault is None:
        from core.vault import Vault
        app.state.vault = Vault(cfg.db_path)
    return app.state.vault


async def get_generator(request: Request):
    """Get wallet generator from app state."""
    app = request.app
    if not hasattr(app.state, "generator") or app.state.generator is None:
        from wallet_engine.generator import WalletGenerator
        app.state.generator = WalletGenerator(vault_password=cfg.vault_password)
    return app.state.generator


async def get_key_store(request: Request):
    """Get key store from app state."""
    app = request.app
    if not hasattr(app.state, "key_store") or app.state.key_store is None:
        from core.auth import KeyStore
        app.state.key_store = KeyStore(cfg.keys_path)
    return app.state.key_store


async def get_audit(request: Request):
    """Get audit trail from app state."""
    app = request.app
    if not hasattr(app.state, "audit") or app.state.audit is None:
        from core.audit import AuditTrail
        app.state.audit = AuditTrail(cfg.audit_path)
    return app.state.audit


async def get_license(request: Request):
    """Get license manager from app state."""
    app = request.app
    if not hasattr(app.state, "license") or app.state.license is None:
        from core.license import LicenseManager
        app.state.license = LicenseManager()
    return app.state.license


async def get_proof(request: Request):
    """Get proof of generation from app state."""
    app = request.app
    if not hasattr(app.state, "proof") or app.state.proof is None:
        from core.proof import ProofOfGeneration
        app.state.proof = ProofOfGeneration(cfg.data_dir / "proof.db")
    return app.state.proof
