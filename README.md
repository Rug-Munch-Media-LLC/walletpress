# WalletPress

> Part of **Rug Munch Media LLC** — Wyoming-based crypto intelligence platform.

## What

Wallet-as-a-service. Wallet engine, x402 service, chain vault, hosting. CLI for wallet management. Production-grade.

## Type
`backend` · **Python 3.12 + FastAPI**

## Quickstart
```bash
make install        # install deps
make dev            # start dev server
make test           # run tests
make lint           # lint + format
make ci             # full CI pipeline
```

## Documentation
- [AGENTS.md](AGENTS.md) — AI agent contract
- [ARCHITECTURE.md](ARCHITECTURE.md) — technical architecture
- [PLAN.md](PLAN.md) — current sprint
- [ROADMAP.md](ROADMAP.md) — long-term direction
- [STATUS.md](STATUS.md) — where we are RIGHT NOW
- [DEVELOPMENT.md](DEVELOPMENT.md) — dev workflow
- [DEPLOYMENT.md](DEPLOYMENT.md) — how to deploy
- [TESTING.md](TESTING.md) — test strategy
- [SECURITY.md](SECURITY.md) — security model
- [DECISIONS.md](DECISIONS.md) — architecture decision records

## Open-Core Model

This repo follows the open-core model. Core wallet engine code is BSL-licensed
(free for non-production use). The RugMunch managed platform at rugmunch.io
includes enterprise wallet infrastructure, key management, and admin features.

See [OPEN-CORE.md](OPEN-CORE.md) for details.

## Standards
This repo follows Rug Munch Media LLC fleet standards:
[github.com/RugMunchMedia/standards](https://github.com/RugMunchMedia/standards)

## Repository
- Source of truth: `https://github.com/RugMunchMedia/walletpress`
- Mirrors: Codeberg, GitLab, HuggingFace

## FAQ

See [docs/FAQ.md](docs/FAQ.md) for frequently asked questions.
