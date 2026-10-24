# walletpress

Wallet infrastructure you can run yourself: an encrypted key vault, HD address
generation, an x402 payment service, and a WordPress plugin that puts a wallet
and a paywall on any WP site.

**Status:** beta — the API and the vault format are stable, the WordPress plugin
is still moving. **Licence:** Business Source License 1.1, see [LICENSE](LICENSE).

Canonical: https://git.rugmunch.io/RugMunchMedia/walletpress

## Quickstart

Python 3.11+ and Postgres. The vault password is required, not optional.

```bash
git clone https://git.rugmunch.io/RugMunchMedia/walletpress.git
cd walletpress
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env      # set WP_VAULT_PASSWORD and WP_ADMIN_KEY
make migrate
make dev
```

API on `http://localhost:8000` (override with `WP_PORT`). Two console scripts
are installed from `backend/pyproject.toml`: `walletpress` (admin CLI) and
`wp-verify-receipt` (checks a payment receipt).

Compose needs the vault password exported first — it will not generate one for
you:

```bash
export WP_VAULT_PASSWORD='...' WP_ADMIN_KEY='...'
docker compose up -d
```

Install the WordPress plugin from `wp-plugin/` by copying the directory into
`wp-content/plugins/` and activating it, then point its settings at your API base
URL and admin key.

## What it does

- **Encrypted vault.** Private keys and seed material are sealed with a password
  you supply at boot; the vault file is useless without it. There is no recovery
  path and no escrow.
- **Address generation.** HD derivation for the supported chains, with
  `ADDRESS_GENERATION.md` documenting the derivation paths so you can verify an
  address independently.
- **x402 service.** Metered endpoints that issue a 402, verify the payment, and
  release the resource — the same flow `x402-coffer` implements at larger scale.
- **WordPress plugin.** Wallet connect, gated content and payment widgets, so a
  WP site can charge for posts without a third-party processor.
- **Admin CLI.** `walletpress` covers key lifecycle and address inspection
  without going through the API.

## How it is put together

```
wp-plugin/         WordPress side (PHP): settings, shortcodes, paywall UI
backend/walletpress/
  ├── adapters/    chain RPC and storage adapters
  ├── agent/       background workers
  ├── wallet*      vault, derivation, signing
  └── alembic/     schema migrations
  walletpress_cli.py   admin CLI entry point
```

## Configuration

| Variable | Purpose |
|---|---|
| `WP_VAULT_PASSWORD` | decrypts the vault; required, no default |
| `WP_ADMIN_KEY` | admin API credential |
| `WP_HOST`, `WP_PORT` | bind address |
| `WP_DATA_DIR` | vault and database files on disk |
| `WP_CORS_ORIGINS` | allowlist for browser clients |
| `WP_RATE_LIMIT`, `WP_MAX_BATCH` | request and batch caps |
| `WP_AI_PROVIDER`, `WP_AI_API_KEY`, `WP_AI_MODEL` | optional AI features; unset disables them |

## Known limits

- Losing `WP_VAULT_PASSWORD` loses the funds. This is the design, not a bug.
- BSL 1.1: you may self-host and modify it, but you may not offer it as a
  competing hosted wallet service. The licence text is the authority.
- Testnet only unless you have deliberately configured mainnet RPC endpoints and
  accepted the risk. There is no mainnet guard rail in code.
- The WordPress plugin is the least mature surface here. Expect to read the PHP.

## Development

```bash
make lint && make typecheck && make test
make check        # lint + typecheck + security + test
```

## Licence

Business Source License 1.1. See [LICENSE](LICENSE) for the change date and the
additional use grant.
