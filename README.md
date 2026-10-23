# WalletPress

> Multi-chain wallet engine, x402 service and chain vault: 55 chains, BIP39 derivation, AES-256 vault and a WordPress plugin.

**License:** [BSL 1.1](LICENSE) · **Canonical:** https://git.rugmunch.io/RugMunchMedia/walletpress
**Mirrors:** [GitHub](https://github.com/Rug-Munch-Media-LLC) · [GitLab](https://gitlab.com/rug-munch-media-group) · [Codeberg](https://codeberg.org/RugMunchMedia)

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

## x402 Paid Wallets (coffer facilitator)

Paid wallet printing (`backend/x402_service.py`, mounted at
`/api/v1/marketplace/*`) is gated on **x402-coffer** — a self-hosted x402
payment facilitator configured with the treasury receiving wallets — instead
of in-house on-chain verification:

- `POST {X402_FACILITATOR_URL}/v1/x402/verify` — verify a reported payment
- `POST {X402_FACILITATOR_URL}/v1/x402/settle` — settle an EIP-3009 authorization

Set `X402_FACILITATOR_URL` (and optionally `X402_MERCHANT_KEY` for
auth-proxied deployments) in the backend env — see `backend/.env.example`.
Local policy stays ABOVE the facilitator: `MIN_ORDER_USD`, per-client
free-tier tracking and KeyStore credit auth are enforced server-side first,
and the coffer's echoed network/asset/amount is confirm-matched against the
quoted order before keys are returned. Fail-closed: an unreachable coffer
means HTTP 402, never an unverified fulfillment.

Parity note: this mirrors the pry-scraper billing confirm pattern
(`src/pry/api/routers/commerce/billing_subscription.py`) — a payment only
counts once the invoice record's recipient, amount and asset match the
verified on-chain payment.

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
