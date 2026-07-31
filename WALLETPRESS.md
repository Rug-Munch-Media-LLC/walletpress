# WalletPress

> Multi-chain wallet generation & management for humans and AI agents.

**Tagline:** Self-hosted. Open source. Agentic.

---

## What it is

WalletPress is an MIT-licensed platform that generates, stores, and manages crypto wallets across **55 blockchains** (BTC, ETH family, Solana, TRON, Cosmos, Substrate, Ed25519 chains, and more). It exposes the same operations through four surfaces:

- **REST API** (`/docs`) — for integrations
- **MCP server** (`/mcp/sse`) — for AI agents
- **CLI** (`walletpress ...`) — for operators
- **WordPress plugin** — for the 43% of the web

---

## The four-pillar design

1. **Cryptographic determinism.** Every wallet is BIP39/BIP32/BIP44 standard. Same mnemonic + path = same address on every wallet software in the world. No secret sauce.
2. **Defense in depth.** AES-256-GCM + Argon2id at rest. SHA-256-chained audit log. Address allow/block lists. Per-chain tier.
3. **Agent-first.** Every operation is an MCP tool. The AI agent plans with `agent_plan`, asks for confirmation with `agent_confirm`, executes with `agent_execute`.
4. **Proof of Generation.** Every wallet gets a Merkle-tree attestation. The root can be committed for permanent proof that we generated the wallet at that time with that code version.

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
│   └── plugins/            # DeFi integrations
├── wp-plugin/              # WordPress plugin (token gating, payments, login)
├── walletpress-mcp/        # Standalone MCP server (talks to any backend)
├── installers/             # docker-compose.prod.yml
├── scripts/                # utility scripts
└── docs/                   # markdown documentation
```

---

## Canonical documentation

Start here, then read in order:

| Doc | What's in it |
|-----|--------------|
| **WALLETPRESS.md** (this file) | Product summary, where to find things |
| `ARCHITECTURE.md` | System design, modules, roadmap, moving-forward plan |
| `SECURITY.md` | Threat model, crypto rules, auth/authz |
| `AUDIT.md` | Bugs by severity, what to fix, verification commands |
| `ADDRESS_GENERATION.md` | Per-chain truth table — which chains actually work |
| `BUILDER.md` | Daily workflow, "what's next" list, agent rules |
| `CONTRIBUTING.md` | How to contribute |

---

## Quickstart (developer)

```bash
git clone https://github.com/cryptorugmuncher/walletpress.git
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
      "headers": { "X-Admin-Key": "..." },
      "env": { "WP_API_KEY": "wp_..." }
    }
  }
}
```

> **Security note:** every `/mcp` route requires the `WP_ADMIN_KEY` admin key
> (sent as `X-Admin-Key`, `Authorization: Bearer`, or `X-API-Key` header).
> The MCP server can decrypt private keys and sweep wallets — do not expose
> it without the admin key.

---

## Repository conventions

- **One repo per product.** Separate repos with separate release cadences.
- **Conventional commits.** `feat(scope):`, `fix(scope):`, `chore:`, `docs:`. Mandatory.
- **Push to primary remote**, then mirror to others.
- **Tag releases** with `vX.Y.Z`. Pre-release: `-beta`, `-audit`, `-rcN`.
- **No .env in git.** Use environment variables or a secrets manager.
