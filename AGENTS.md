# AGENTS.md — WalletPress

> AI agent contract. Read this before touching anything in this repo.

## Status
canonical · owner=crmuncher · last_updated=2026-07-02

## What This Repo Is
Wallet-as-a-service. Wallet engine, x402 service, chain vault, hosting. CLI for wallet management. Production-grade.

## Type
`backend` · language=Python 3.12 + FastAPI

## Where It Lives
- Source: `https://github.com/RugMunchMedia/walletpress`

## Built With
- Standards: [github.com/RugMunchMedia/standards](https://github.com/RugMunchMedia/standards)
- Toolchain: [TOOLCHAIN.md](https://github.com/RugMunchMedia/standards/raw/main/TOOLCHAIN.md)
- Conventions: [CONVENTIONS.md](https://github.com/RugMunchMedia/standards/raw/main/CONVENTIONS.md)

## Components
- `app/`: FastAPI source (adapters, agent, cli, core, plugins, routers)

## Dependencies
- postgresql (data store)
- redis (cache + queue)

## 🚨 CRITICAL RULES

1. **No nested repos.** Don't commit other complete project trees inside this one.
2. **No secrets.** Never commit `.secrets/`, `.env`, `*.pem`, `*.key`, `*.crt`.
3. **No data blobs.** Don't commit `*.zip`, `*.parquet`, model weights, sqlite files.
4. **No broken files.** Shell heredoc accidents must be caught before commit.
5. **No duplicate scaffolds.** If a `backend/` or `frontend/` subdir exists at root, it's either THE app or bloat.
6. **Update STATUS.md before committing.** Builders must know where we are.
7. **Read DECISIONS.md before architectural changes.** Don't repeat rejected designs.

## Commands
```bash
make install       # install deps
make dev           # dev server
make test          # tests
make lint          # ruff + format check
make typecheck     # mypy strict
make security      # bandit + gitleaks
make ci            # full pipeline
make commit        # conventional commit
make clean         # remove build artifacts
```

## Architecture
See [ARCHITECTURE.md](ARCHITECTURE.md). Update it when components change.

## Plan
[PLAN.md](PLAN.md) shows current sprint. Update weekly.

## Status
[STATUS.md](STATUS.md) shows where we are RIGHT NOW. Update before each commit.

## Owners
- Primary: crmuncher
- Backup: TBD

## Related Repos
See [standards/PRODUCTS.md](https://github.com/RugMunchMedia/standards/raw/main/PRODUCTS.md).

## Open-Core Protection

This repo is BSL-licensed (free for non-production use). The code here
demonstrates wallet management patterns — it is NOT the complete RugMunch
production wallet infrastructure. The managed platform at rugmunch.io
includes production key management, enterprise SSO/RBAC, and admin features.

See [METHODOLOGY-PROTECTION.md](https://github.com/RugMunchMedia/standards/blob/main/METHODOLOGY-PROTECTION.md)
for details on what information belongs in public vs private repos.

## Git Policy

This repo:
- Classification: OPEN SOURCE
- Remotes: codeberg + github + gitlab + radicle (primary)
- Commits: type(scope): description
- Never commit: .env, secrets, internal IPs, security reports
