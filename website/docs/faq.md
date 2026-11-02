---

title: "FAQ — Frequently Asked Questions"
description: "Answers to common questions about WalletPress: licensing, security, chains, pricing, self-hosting, and more."
keywords: [faq, frequently asked questions, walletpress, licensing, security, pricing, self-hosted]
unlisted: false
---

// WpBadge import removed for MDX compatibility

*Live*

---

## General

### What is WalletPress?

WalletPress is a **self-hosted, 55-chain wallet infrastructure** that you run on your own servers. It provides wallet generation, management, and signing through four interfaces: REST API, MCP server (for AI agents), CLI, and WordPress plugin. Built on BIP39/44 standards with AES-256-GCM vault encryption, Argon2id key derivation, and HITL (human-in-the-loop) approval on every mutating operation.

### Who is it for?

- **Developers** building crypto products who need wallet infrastructure without vendor lock-in
- **AI agent builders** who need MCP tools for wallet operations with HITL safety
- **WordPress site owners** wanting token gating, crypto payments, and wallet login
- **Trading teams** automating multi-chain wallet operations
- **Anyone** who believes "not your keys, not your coins" should apply to infrastructure too

### How is this different from Turnkey, Privy, or Coinbase Cloud?

| Aspect        | WalletPress                      | Turnkey/Privy/Coinbase Cloud |
| ------------- | -------------------------------- | ---------------------------- |
| **Hosting**   | Your servers (self-hosted)       | Their cloud (SaaS)           |
| **Keys**      | Never leave your infra           | Stored in their HSMs         |
| **Pricing**   | $199 one-time / $0.01 per wallet | $500+/mo minimums + usage    |
| **Chains**    | 55 (all major + custom)          | 10-20 typically              |
| **License**   | BSL 1.1 (source available)       | Proprietary                  |
| **AI Agents** | Native MCP with HITL             | Limited/none                 |
| **WordPress** | Native plugin                    | Not available                |

### Is it open source?

**Source-available under BSL 1.1 (Business Source License 1.1).** The license converts to MIT after 4 years (2030). You can read, modify, self-host, and audit the code. You cannot resell it as a managed service without a commercial license. See [LICENSING.md](../licensing.md) for details.

---

## Security

### Where are my keys stored?

**On your servers, in your vault.** The AES-256-GCM encrypted vault lives in your PostgreSQL database (or SQLite for dev). The encryption key is derived from your `VAULT_KEY` environment variable using Argon2id. We never see your keys, your mnemonics, or your vault data.

### What if someone hacks my server?

They get encrypted blobs. Without `VAULT_KEY` (32-byte base64, derived via Argon2id with 64MB memory cost), the vault is mathematically infeasible to decrypt. The kill switch (`POST /api/v1/admin/vault/seal`) can zero all keys in memory instantly.

### Can you (Rug Munch Media) access my wallets?

**No.** We don't host your vault. We don't have your `VAULT_KEY`. We don't run a key escrow. The only thing we see is if you use our hosted tier — and even then, the vault encryption happens client-side before data hits our API.

### What's HITL and why does it matter?

**Human-In-The-Loop.** Every mutating operation (generate wallet, derive address, sign transaction, sign message) requires explicit human approval. For API: you approve via dashboard or API. For MCP: the agent proposes, you approve/reject/modify, then it executes. This prevents AI agents from draining wallets, prevents compromised API keys from draining wallets, and creates an audit trail of _who approved what_.

---

## Chains & Features

### Which chains are supported?

**55 chains and counting:** All major EVM (Ethereum, Arbitrum, Optimism, Base, Polygon, BNB, Avalanche, etc.), Solana, Bitcoin, Cosmos ecosystem (8 chains), Polkadot/Substrate (6 chains), TRON, Ed25519 generic (Cardano, Algorand, Stellar). Full list: [Chains Supported](../chains-supported.md).

### Can I add my own chain?

**Yes.** Add to `CHAINS.yaml` with CAIP-2 ID, derivation path, RPC endpoints, and feature flags. Run `walletpress chains reload`. No code changes needed.

### What derivation paths are used?

Standard BIP44:
- **EVM:** `m/44'/60'/0'/0/0` (coin type 60)
- **Solana:** `m/44'/501'/0'/0'` (coin type 501)
- **Bitcoin:** `m/84'/0'/0'/0/0` (Native SegWit, BIP84)
- **Cosmos:** `m/44'/118'/0'/0/0` (coin type 118)
- **Polkadot:** `m/44'/354'/0'/0/0` (coin type 354)

Customizable per wallet or globally in config.

### What token standards are supported?

| Chain    | Fungible                  | NFTs              | Multi-token |
| -------- | ------------------------- | ----------------- | ----------- |
| EVM      | ERC-20, ERC-777, ERC-4626 | ERC-721, ERC-1155 | ✅          |
| Solana   | SPL Token, Token-2022     | Metaplex, cNFTs   | ✅          |
| Cosmos   | CW20                      | CW721             | ✅          |
| Polkadot | PSP22                     | PSP34             | ✅          |

---

## Pricing & Licensing

### How much does it cost?

| Tier                        | Price         | Best For                                 |
| --------------------------- | ------------- | ---------------------------------------- |
| **WordPress Plugin (Free)** | $0            | 3 chains, basic token gating/payments    |
| **Pro Self-Hosted**         | $199 one-time | Devs wanting full control, all 55 chains |
| **Hosted**                  | $29/month     | Teams wanting zero-ops, SLA              |
| **x402 Marketplace**        | $0.01/wallet  | Bots, AI agents, pay-per-use             |

### What's the BSL 1.1 license?

**Business Source License 1.1.** You can:
- ✅ Self-host for internal use
- ✅ Modify the code
- ✅ Audit the code
- ✅ Use in commercial products (if self-hosted)
- ❌ Sell as a managed service (SaaS) without commercial license
- ❌ Remove license notices

Converts to **MIT** on **2030-01-01** (4 years after release).

### Do I need a license for each server?

**No.** One Pro license covers unlimited servers, unlimited team members, unlimited wallets. The license is per organization, not per instance.

### What about the x402 marketplace?

**Pay-per-use at $0.01 per wallet generation.** No monthly fees, no minimums. AI agents pay on-chain via USDC (Solana/Base/Arbitrum/Ethereum). Free tier: 100 generations/day per API key. Referral program: 20% revenue share for 12 months.

---

## Self-Hosting

### What are the requirements?

| Component  | Minimum                   | Recommended                |
| ---------- | ------------------------- | -------------------------- |
| CPU        | 2 cores                   | 4+ cores                   |
| RAM        | 2 GB                      | 4+ GB                      |
| Disk       | 10 GB                     | 50+ GB (SSD)               |
| OS         | Linux (any modern distro) | Ubuntu 22.04+ / Debian 12+ |
| Docker     | 24+                       | Latest                     |
| PostgreSQL | 14+                       | 16+                        |
| Redis      | 7+                        | 7+                         |

### Can I run it on Kubernetes?

**Yes.** Helm chart available in `deploy/helm/`. Supports:
- Horizontal pod autoscaling
- Pod disruption budgets
- Network policies
- Prometheus/Grafana monitoring
- Vault integration (external secrets)

### What about backups?

**Built-in:** Nightly PostgreSQL dumps, vault encryption export, Arweave proof index. Configure `BACKUP_S3_BUCKET` for offsite. Restore tested weekly in CI.

### How do I update?

```bash
# Docker
docker compose pull && docker compose up -d

# Binary
curl -L https://github.com/RugMunchMedia/walletpress/releases/latest/download/walletpress-linux-amd64 -o walletpress
chmod +x walletpress && sudo mv walletpress /usr/local/bin/

# Database migrations run automatically on startup
```

---

## AI Agents & MCP

### What is MCP?

**Model Context Protocol** — an open standard for AI agents to use tools. WalletPress exposes 30+ wallet tools (generate, derive, sign, manage) via MCP with built-in HITL.

### Which frameworks are supported?

- **LangChain** (Python/JS)
- **CrewAI**
- **Eliza (AI16z)**
- **OpenAI Agents SDK**
- **Vercel AI SDK**
- **Any MCP-compatible client**

### How does HITL work with agents?

```python
# Agent proposes
plan = await mcp.agent_plan({"action": "sign_transaction", ...})

# Human reviews in dashboard or CLI
if human_approves(plan):
    result = await mcp.agent_execute(plan.id)
```

The agent **cannot execute** without explicit approval. You see: action, params, risk level, estimated cost, Arweave proof preview. You approve/reject/modify.

### Can agents run autonomously?

**Only for read operations** (list wallets, get balances, verify proofs). All mutating operations require HITL. This is a design constraint, not a limitation.

---

## WordPress Plugin

### What's free vs paid?

| Feature             | Free (3 chains)         | Pro ($199)    |
| ------------------- | ----------------------- | ------------- |
| Chains              | Ethereum, Polygon, Base | All 55        |
| Token Gating        | ERC-20, ERC-721         | All standards |
| Crypto Payments     | USDC, ETH               | 50+ tokens    |
| Wallet Login        | SIWE                    | SIWE + Solana |
| WooCommerce         | ❌                      | ✅            |
| Elementor/Gutenberg | ❌                      | ✅            |
| Webhooks            | ❌                      | 20+ events    |

### Does it work with page builders?

**Pro only:** Native Elementor widgets and Gutenberg blocks. Drag, drop, configure — no code.

### Is it compatible with caching plugins?

**Yes.** Token balances cached 5 min (configurable). All wallet interactions async via AJAX. Assets: ~15KB CSS+JS, deferred, no jQuery dependency.

---

## Troubleshooting

### "Vault locked" / "VAULT_KEY mismatch"

1. Ensure `VAULT_KEY` env var matches the one used to encrypt the vault
2. If lost: **data is unrecoverable** (by design). Restore from backup.
3. Check `docker compose logs walletpress` for "vault: locked" message

### "Database connection refused"

```bash
# Check PostgreSQL
docker compose logs postgres

# Check connection string
echo $DATABASE_URL
# Should be: postgresql://user:pass@postgres:5432/walletpress
```

### "Redis connection refused"

```bash
docker compose logs redis
# Ensure REDIS_URL=redis://redis:6379
```

### "MCP connection failed"

```bash
# Check MCP endpoint
curl http://localhost:8010/mcp/sse
# Should return SSE stream

# Check auth
curl -H "Authorization: Bearer $TOKEN" http://localhost:8010/mcp/sse
```

### "x402 payment stuck"

1. Check transaction on-chain (Solscan/Basescan/Etherscan)
2. Verify `X-Payment` header format (JWT with ES256)
3. Check invoice expiry (10 min default)
4. Webhook logs: `docker compose logs walletpress | grep x402`

---

## Getting Help

- **Documentation:** This site (search with `Ctrl+K`)
- **GitHub Issues:** [codeberg.org/RugMunchMedia/walletpress/issues](https://codeberg.org/RugMunchMedia/walletpress/issues)
- **Telegram:** [t.me/walletpress](https://t.me/walletpress)
- **Email:** support@walletpress.cc
- **Security:** security@walletpress.cc (or Immunefi)

---

## Still Have Questions?

**Email us:** support@walletpress.cc — we usually respond within 24 hours on business days.

**For security issues:** security@walletpress.cc or [Immunefi](https://immunefi.com/bounty/walletpress) — up to $50,000 for critical vulns.
