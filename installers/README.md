# WalletPress — Paid Installation Methods

These installers are included with the Pro license download.
They are NOT in the open source repository.

## Method 1: CLI (recommended)

One command. Works on Ubuntu, Debian, macOS, RHEL, Fedora.

```bash
walletpress deploy
```

What it does:
- Detects OS and package manager
- Installs Python 3.12, OpenSSL 3.x, SQLite 3
- Creates virtual environment
- Installs all dependencies
- Generates secure credentials (admin key, vault password)
- Installs Pro license key
- Pre-configures RPC endpoints for all 55 chains
- Sets up systemd (Linux) or launchd (macOS) service
- Optionally configures nginx + Let's Encrypt SSL
- Sets up daily backup schedule
- Starts the service
- Prints admin URL and credentials

## Method 2: Docker

For users who prefer containerized deployments.

```bash
walletpress deploy --docker
# or manually:
docker compose -f docker-compose.prod.yml up -d
```

Includes:
- WalletPress service (production-optimized)
- PostgreSQL (persistent storage)
- Redis (rate limiting + caching)
- Nginx (reverse proxy + SSL termination)
- Certbot (automatic SSL renewal)
- Volumes for vault, proofs, backups

## Method 3: pip install

For developers integrating WalletPress into existing Python applications.

```bash
pip install walletpress
walletpress init
walletpress serve --port 8010
```

Note: pip install gives you the engine. No RPC configuration,
no SSL, no systemd, no backups. You handle infrastructure yourself.
