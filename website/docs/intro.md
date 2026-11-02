---

title: "WalletPress — 55-Chain Wallet Infrastructure You Self-Host"
description: "BIP39 deterministic generation, AES-256-GCM vault, Argon2id key derivation, HITL confirmation on every write. Four surfaces: REST API, MCP server (30+ tools), CLI, WordPress plugin. x402 marketplace at $0.01/wallet. Proof of generation committed to Arweave. BSL 1.1 licensed."
keywords: [crypto wallet engine, bip39, multi-chain wallets, wallet api, ai agent wallets, walletpress, self-hosted, x402, mcp, wordpress plugin]
unlisted: false
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';


<span class="wp-badge wp-badge--coming">Early Access — full launch incoming</span>

**55 chains. One platform. Self-hosted. Agentic. BSL 1.1 licensed.**

WalletPress generates, stores, and manages crypto wallets across 55 blockchains — Bitcoin, Ethereum and every EVM chain, Solana, TRON, Cosmos, Substrate, Ed25519 chains, and more. Same operations available through four surfaces: REST API, MCP server, CLI, and WordPress plugin.

---

## Why WalletPress Exists

Every crypto project needs wallet operations. Every AI agent needs to hold keys. Every WordPress site wants crypto payments. The options today are:

| Option                                        | Problem                                                                       |
| --------------------------------------------- | ----------------------------------------------------------------------------- |
| **Custodial services** (Coinbase, Fireblocks) | You don't own keys. They can freeze. They charge 0.5-2% + monthly fees.       |
| **SaaS wallet APIs** (Turnkey, Privy)         | Vendor lock-in. Monthly minimums $500+. Keys leave your infrastructure.       |
| **Rolling your own**                          | 6+ months to get BIP39/44 right across 55 chains. Security audit costs $50k+. |
| **Hardware wallets only**                     | Great for humans. Terrible for automation. No API, no MCP, no x402.           |

**WalletPress is the fifth option:** Self-hosted, BIP39-standard, deterministic, auditable, with four interfaces (REST, MCP, CLI, WordPress) and x402 pay-per-use so you only pay for what you generate.

---

## What It Actually Does

### Wallet Generation Engine

BIP39/BIP32/BIP44 standard. Deterministic. Same mnemonic + derivation path = same address on every wallet software in the world. No secret sauce. No vendor lock-in. You own your keys. We never custody.

Generate a wallet for any of 55 chains with a single API call, CLI command, or MCP prompt.

- **POST** `/api/v1/wallets` — Generate new wallet
- **POST** `/api/v1/wallets/derive` — Derive address at path
- **GET** `/api/v1/wallets/{id}` — Get wallet details
- **GET** `/api/v1/wallets/{id}/addresses` — List all derived addresses

### Secure Vault

AES-256-GCM encryption at rest. Argon2id key derivation. SHA-256-chained audit log. HITL (human-in-the-loop) confirmation on every write. Kill switch. Address allow/block lists. Spending limits. Per-chain tier controls.

Defense in depth. Not a hot wallet. Not a custodial service. Your infrastructure, your keys, your vault.

### x402 Micropayment Marketplace

$0.01 per wallet generation. Pay-per-use API. Bots and automation pay per wallet — no monthly SaaS subscription. The marketplace routes payments through x402 protocol with referral revenue sharing.

- **POST** `/api/v1/x402/wallet` — Generate wallet via x402

### AI Agent Orchestrator

Every wallet operation is an MCP tool — 30+ tools available to AI agents (Claude Code, opencode, Cursor, any MCP-compatible client). The agent plans with `agent_plan`, asks for confirmation with `agent_confirm`, executes with `agent_execute`. The HITL flow is the agent's moral compass.

Adapters for: LangChain, CrewAI, Eliza, OpenAI Agents, Vercel AI.

### Proof of Generation

Every generated wallet gets a Merkle-tree attestation. The root is committed to Arweave for permanent, immutable proof that a specific wallet was generated at a specific time with a specific code version. Auditable. Verifiable. Forever.

### WordPress Plugin

Free tier: 3 chains. Token gating, crypto payments, wallet-based login for any WordPress site. The funnel into the ecosystem — give it away, then scale up.

---

## Chains Supported (55)

<details>
<summary><strong>Click to expand full chain list</strong></summary>

<div class="wp-chain-list">
  <span class="wp-chain">BTC</span>
  <span class="wp-chain">Ethereum</span>
  <span class="wp-chain">Arbitrum</span>
  <span class="wp-chain">Optimism</span>
  <span class="wp-chain">Base</span>
  <span class="wp-chain">Polygon</span>
  <span class="wp-chain">BNB Chain</span>
  <span class="wp-chain">Avalanche</span>
  <span class="wp-chain">Fantom</span>
  <span class="wp-chain">Gnosis</span>
  <span class="wp-chain">Celo</span>
  <span class="wp-chain">Solana</span>
  <span class="wp-chain">TRON</span>
  <span class="wp-chain">Cosmos Hub</span>
  <span class="wp-chain">Osmosis</span>
  <span class="wp-chain">Juno</span>
  <span class="wp-chain">Polkadot</span>
  <span class="wp-chain">Kusama</span>
  <span class="wp-chain">Substrate (generic)</span>
  <span class="wp-chain">Ed25519 (generic)</span>
  <span class="wp-chain">+ 35 more</span>
</div>

Full chain registry in `CHAINS.yaml` — open-source, auditable, extensible.
</details>

---

## Delivery Tiers

*See pricing table below.*

---

## Quickstart

<Tabs>
<TabItem value="docker" label="Docker (Recommended)" default>
```bash
docker run -d \
  -p 8010:8010 \
  -e VAULT_KEY="$(openssl rand -base64 32)" \
  -e DATABASE_URL="postgresql://user:pass@db:5432/walletpress" \
  -e REDIS_URL="redis://redis:6379" \
  -v walletpress-data:/data \
  walletpress/walletpress:latest
```
</TabItem>
<TabItem value="binary" label="Binary">
```bash
curl -L https://github.com/RugMunchMedia/walletpress/releases/latest/download/walletpress-linux-amd64 -o walletpress
chmod +x walletpress
./walletpress server --config /etc/walletpress/config.yaml
```
</TabItem>
<TabItem value="verify" label="Verify">
```bash
# Health check
curl http://localhost:8010/health

# API docs

open http://localhost:8010/docs

# Generate first wallet

curl -X POST http://localhost:8010/api/v1/wallets\
-H "Content-Type: application/json"\
-d '{"chains": ["ethereum", "solana"], "label": "test-wallet"}'
```
</TabItem>
</Tabs>

---

## Architecture at a Glance


- **BIP39/44 Standard** — Deterministic wallet generation. Same mnemonic + path = same address everywhere. No vendor lock-in.
- **AES-256-GCM Vault** — Encryption at rest with Argon2id key derivation. SHA-256 audit log. Kill switch. HITL on every write.
- **x402 Native** — Pay-per-use via HTTP 402. USDC on Solana/Base/Arbitrum. No API keys, no monthly bills.
- **MCP Server (30+ tools)** — Full wallet ops as MCP tools. HITL flow: agent_plan → agent_confirm → agent_execute.
- **Arweave Proofs** — Merkle-tree attestation for every wallet. Root committed to Arweave. Immutable, forever.
- **WordPress Plugin** — Free tier (3 chains). Token gating, crypto payments, wallet login. Funnel to Pro.


---

## Four Surfaces, One Engine

| Surface | Use Case | Auth | Rate Limit |
|---------|----------|------|------------|
| **REST API** | Backend integration, automation | Bearer token | 100 req/s |
| **MCP Server** | AI agents, LangChain, CrewAI | Session-based | 50 req/s |
| **CLI** | Human operators, scripts | Config file | Unlimited |
| **WordPress** | Token gating, payments, login | WP nonce + JWT | WP settings |

---

## Next Steps

- [Quickstart with Docker →](quickstart/docker.md)
- [API Reference →](api/wallet-generation.md)
- [MCP Server Setup →](mcp/overview.md)
- [WordPress Plugin Install →](wordpress/installation.md)
- [Security Model →](security/overview.md)
- [Deployment Guide →](deployment/self-hosted.md)

---

## Get Help

- **Documentation:** This site (search with `Ctrl+K`)
- **API Reference:** [API Docs](api/wallet-generation.md)
- **GitHub:** [codeberg.org/RugMunchMedia/walletpress](https://codeberg.org/RugMunchMedia/walletpress)
- **Telegram:** [t.me/walletpress](https://t.me/walletpress)
- **Security:** [Responsible Disclosure](security/responsible-disclosure.md)```
