"""Initial vault schema — wallets, rotations, FTS, version tracking.

Revises: None (first migration)
Create Date: 2026-06-30
"""
from __future__ import annotations
from collections.abc import Sequence

from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            id TEXT PRIMARY KEY,
            chain TEXT NOT NULL,
            address TEXT NOT NULL,
            label TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            wallet_group TEXT DEFAULT '',
            created_at REAL NOT NULL,
            encrypted_key TEXT DEFAULT '',
            public_key TEXT DEFAULT '',
            derivation_path TEXT DEFAULT '',
            hd_path TEXT DEFAULT '',
            mnemonic_encrypted TEXT DEFAULT '',
            encrypted INTEGER DEFAULT 0,
            balance_usd REAL DEFAULT 0.0,
            notes TEXT DEFAULT '',
            updated_at REAL DEFAULT 0
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_wallets_chain ON wallets(chain)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_wallets_address ON wallets(address)")
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS wallets_fts USING fts5(
            id, chain, address, label, notes,
            content='wallets',
            content_rowid='rowid'
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS rotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id TEXT NOT NULL,
            new_address TEXT NOT NULL,
            rotated_at REAL NOT NULL,
            reason TEXT DEFAULT '',
            FOREIGN KEY(wallet_id) REFERENCES wallets(id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS _schema_version (
            version INTEGER PRIMARY KEY,
            applied_at REAL NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rotations")
    op.execute("DROP TABLE IF EXISTS wallets_fts")
    op.execute("DROP TABLE IF EXISTS wallets")
    op.execute("DROP TABLE IF EXISTS _schema_version")
