# WalletPress

> Multi-chain wallet generation & management for humans and AI agents.

**Tagline:** Self-hosted. Open source. Agentic.

---

## What it is

WalletPress is an MIT-licensed platform that generates, stores, and manages crypto wallets across **55 blockchains** (BTC, ETH family, Solana, TRON, Cosmos, Substrate, Ed25519 chains, and more). It exposes the same operations through four surfaces:

- **REST API** (`/docs`) — for integrations
- **MCP server** (`/mcp/sse`) — for AI agents (Claude Code, opencode, Cursor)
- **CLI** (`walletpress ...`) — for operators
- **WordPress plugin** — for the 43% of the web

The product has three delivery tiers:

| Tier | Price | Audience |
|------|-------|----------|
| **WordPress plugin** | Free (3 chains) | Anyone with a WP site — the funnel |
| **Pro self-hosted** | $199 one-time | Devs who want control |
| **Hosted** | $29/mo | Everyone else — zero-config |
| **x402 API marketplace** | $0.01/wallet | Bots and automation |

Operator: **Rug Munch Media LLC**.

---

## The four-pillar design

1. **Cryptographic determinism.** Every wallet is BIP39/BIP32/BIP44 standard. Same mnemonic + path = same address on every wallet software in the world. No secret sauce.
2. **Defense in depth.** AES-256-GCM + Argon2id at rest. SHA-256-chained audit log. HITL on every write. Kill switch. Address allow/block lists. Spending limits. Per-chain tier.
3. **Agent-first.** Every operation is an MCP tool. The AI agent plans with `agent_plan`, asks for confirmation with `agent_confirm`, executes with `agent_execute`. The HITL flow is the agent's moral compass.
4. **Proof of Generation.** Every wallet gets a Merkle-tree attestation. The root is committed to Arweave for permanent proof that we generated the wallet at that time with that code version.

---

## Repository layout

```
walletpress/
├── backend/                # Python 3.12, FastAPI, SQLite — the engine
│   ├── core/               # vault, auth, audit, proof, agent_safety, ...
│   ├── wallet_engine/      # chains.py (55-chain registry) + generator.py
│   ├── routers/            # FastAPI routes
│   ├── agent/              # orchestrator, MCP server, scheduler, providers
│   ├── adapters/           # agent framework wrappers (langchain, crewai, ...)
│   └── plugins/            # DeFi integrations + referral revenue
├── wp-plugin/              # WordPress plugin (token gating, payments, login)
├── walletpress-mcp/        # Standalone MCP server (talks to any backend)
├── installers/             # docker-compose.prod.yml
├── scripts/                # git-web3-sign.sh
└── docs/                   # markdown documentation
```

---

## Canonical documentation

Start here, then read in order:

| Doc | What's in it |
|-----|--------------|
| **WALLETPRESS.md** (this file) | Product summary, where to find things |
| `ARCHITECTURE.md` | System design, modules, roadmap, moving-forward plan |
| `SECURITY.md` | Threat model, crypto rules, auth/authz, incident response |
| `AUDIT.md` | Bugs by severity, what to fix, verification commands |
| `ADDRESS_GENERATION.md` | Per-chain truth table — which chains actually work |
| `BUILDER.md` | Daily workflow, "what's next" list, agent rules |
| `STRATEGY.md` | Go-to-market, business model |
| `CONTRIBUTING.md` | How to contribute (the old doc) |

**Do not trust** `PROGRESS.md`, `ROADMAP.md`, `ROADMAP_V2.md` without verifying. They claim features that may not exist.

---

## Status (as of 2026-06-30)

**v1.0.0-beta shipped.** Not production-ready. See AUDIT.md for the 6 P0 blockers.

Stable surfaces:
- Wallet generation for ~28 chains (BTC, ETH family, SOL, TRX, NEAR, SUI, APT).
- AES-256-GCM vault with SQLite persistence.
- FastAPI + WebSocket event stream.
- MCP server with 30+ tools.
- CLI for `serve`, `init`, `generate`, `backup`, `restore`, `doctor`.

Unstable / blocked:
- ~17 chains (Cosmos family, Stellar, TON, Tezos, Polkadot, Monero, etc.) produce invalid addresses — see ADDRESS_GENERATION.md. Disabled in next release.
- Hosted mode uses unsalted SHA-256 for passwords. Critical fix in flight.
- x402 marketplace has a credits-bypass bug. Critical fix in flight.
- The 5 ad-framework adapters (langchain, crewai, etc.) are stubs.

---

## Quickstart (developer)

```bash
git clone https://git.rugmunch.io/RugMunchMedia/walletpress.git
cd walletpress
make install      # cd backend && pip install -r requirements.txt
cp backend/.env.example backend/.env
# Edit backend/.env: set WP_ADMIN_KEY and WP_VAULT_PASSWORD
cd backend
python3 -m walletpress_cli serve --port 8010
# Open http://localhost:8010/docs
```

---

## Quickstart (WP plugin)

```bash
# Inside WordPress admin
wp plugin install walletpress --activate
# Settings → WalletPress → paste API URL + key
# Use [wallet_connect], [wallet_gate], [wallet_pay] shortcodes
```

---

## Quickstart (MCP)

In `.opencode/opencode.jsonc` or equivalent:

```json
{
  "mcpServers": {
    "walletpress": {
      "url": "http://localhost:8010/mcp/sse",
      "env": { "WP_API_KEY": "wp_..." }
    }
  }
}
```

Then ask your agent: *"Generate 5 SOL wallets for the airdrop."* The agent uses `agent_plan` → `agent_confirm` → `agent_execute`.

---

## Repository conventions

- **One repo per product.** RMI, Pry, WalletPress are separate repos with separate release cadences.
- **Conventional commits.** `feat(scope):`, `fix(scope):`, `chore:`, `docs:`. Mandatory.
- **Push** to forgejo as primary (`git push origin main`). Multi-remote mirroring via script.
- **Tag releases** with `vX.Y.Z`. Pre-release: `-beta`, `-audit`, `-rcN`.
- **No .env in git.** Use `gopass` for secrets.

---

## See also

- `ARCHITECTURE.md` — system design
- `SECURITY.md` — security model
- `AUDIT.md` — bugs and fixes
- `ADDRESS_GENERATION.md` — chain truth table
- `BUILDER.md` — daily workflow