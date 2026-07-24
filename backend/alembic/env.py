"""Alembic migration environment for WalletPress.

The app uses raw sqlite3 (not SQLAlchemy). Migrations use raw SQL
via op.execute(). This keeps the app free of SQLAlchemy overhead
while still benefiting from Alembic's migration management.

The sqlalchemy.url in alembic.ini is the fallback. This env.py
resolves cfg.db_path at runtime so migrations hit the same DB
the app uses (respecting WP_DATA_DIR).

Usage:
    alembic revision --autogenerate -m "description"
    alembic upgrade head
    alembic downgrade -1
"""

from __future__ import annotations
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the actual database path from app config at runtime.
# Fall back to alembic.ini value if import fails (offline/CI).
try:
    from core.config import cfg
    db_url = f"sqlite:///{cfg.db_path}"
except Exception:
    db_url = config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(url=db_url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Ensure the parent directory exists (SQLAlchemy won't create it)
    db_file = db_url.replace("sqlite:///", "")
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    connectable = create_engine(db_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
