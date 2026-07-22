# AGENTS.md — WalletPress

> AI agent contract. Read this before touching anything in this repo.

## Status
canonical · owner=crmuncher · last_updated=2026-07-02

## What This Repo Is
Wallet-as-a-service. Wallet engine, x402 service, chain vault, hosting. CLI for wallet management. Production-grade.

## Type
`backend` · language=Python 3.12 + FastAPI

## Where It Lives
- Source: `https://git.rugmunch.io/RugMunchMedia/walletpress`
- Deployed: Docker on Talos (/srv/walletpress/)
- Port: 8010

## Built With
- Standards: [git.rugmunch.io/RugMunchMedia/standards](https://git.rugmunch.io/RugMunchMedia/standards)
- Toolchain: [TOOLCHAIN.md](https://git.rugmunch.io/RugMunchMedia/standards/raw/branch/main/TOOLCHAIN.md)
- Conventions: [CONVENTIONS.md](https://git.rugmunch.io/RugMunchMedia/standards/raw/branch/main/CONVENTIONS.md)

## Components
- `app/`: FastAPI source (adapters, agent, cli, core, plugins, routers)

## Dependencies
- postgresql (data store)
- redis (cache + queue)

## 🚨 CRITICAL RULES

1. **No nested repos.** Don't commit other complete project trees inside this one.
2. **No secrets.** Never commit `.secrets/`, `.env`, `*.pem`, `*.key`, `*.crt`. Use gopass.
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
See [standards/PRODUCTS.md](https://git.rugmunch.io/RugMunchMedia/standards/raw/branch/main/PRODUCTS.md).

## Git Policy

See the master Git Policy at /root/AGENTS.md. This repo:
- Classification: OPEN SOURCE
- Remotes: forgejo + codeberg + gitlab + radicle
- Push: git push forgejo main && git push codeberg main && git push gitlab main && rad sync
- Commits: type(scope): description
- Never commit: .env, secrets, internal IPs, security reports
