---

title: "Changelog"
description: "WalletPress release history. All notable changes documented here. Follows Keep a Changelog format."
keywords: [changelog, releases, versions, walletpress, updates]
unlisted: false
---

// WpBadge import removed for MDX compatibility

*Current: v1.2.0*

---

## Version 1.2.0 - 2026-11-02

### Added

- **x402 Marketplace v2** — Pay-per-use wallet generation with USDC on Solana, Base, Arbitrum, Ethereum. Referral revenue sharing (20% for 12 months).
- **Arweave Proof of Generation** — Every wallet gets Merkle-tree attestation committed to Arweave. Immutable, verifiable, auditable.
- **9 New Chains** — Zora, Blast, Mode, Fraxtal, Metis, Kava, Moonbeam, Moonriver, Cronos (EVM). Celestia, Neutron, Stride, Axelar (Cosmos).
- **MCP Tool Expansion** — 30+ tools now available including `x402_generate_wallet`, `verify_proof`, `health_check`.
- **WordPress Plugin Pro** — WooCommerce integration, Elementor widgets, Gutenberg blocks, 20+ webhooks.
- **CLI v2** — `walletpress x402`, `walletpress vault seal/unseal`, `walletpress export/import`, improved scripting output.

### Changed

- **Vault Key Derivation** — Argon2id memory cost increased from 32MB to 64MB for stronger ASIC resistance.
- **Audit Log Chaining** — Now includes operation risk level and actor context in chained hash.
- **Rate Limiting** — Pro tier increased from 50 to 100 req/s. Free tier unchanged at 10 req/s.
- **Docker Images** — Multi-arch (amd64/arm64), distroless base, ~40% smaller.
- **CLI Output** — New `--format json` for all commands, structured error codes for scripting.

### Fixed

- **MCP HITL Race Condition** — Fixed rare case where concurrent approvals could execute twice.
- **Solana Derivation** — Corrected BIP44 coin type from 500 to 501 (BIP44 registered).
- **x402 Invoice Expiry** — Extended from 5 to 10 minutes default.
- **WordPress Plugin** — Fixed nonce verification race in high-concurrency payment flows.
- **CLI Export/Import** — Fixed AES-256-GCM nonce reuse vulnerability in backup encryption.

---

## Version 1.1.0 - 2026-09-15

### Added

- **MCP Server (Beta)** — 25+ tools for AI agents with HITL flow. Adapters for LangChain, CrewAI, Eliza, OpenAI Agents, Vercel AI SDK.
- **Solana Support** — Full SPL Token, SPL Token-2022, Metaplex NFT support. BIP44 coin type 501.
- **Cosmos Ecosystem (8 chains)** — Cosmos Hub, Osmosis, Juno, Injective, Celestia, Neutron, Stride, Axelar.
- **Polkadot/Substrate (6 chains)** — Polkadot, Kusama, Moonbeam, Moonriver, Astar, Substrate generic.
- **TRON Support** — TRC-10, TRC-20 tokens.
- **Ed25519 Chains** — Cardano, Algorand, Stellar via generic Ed25519 derivation.
- **Arweave Proof of Generation** — Merkle-tree attestation for every wallet, committed to Arweave.
- **CLI v1** — Full wallet operations from terminal: generate, derive, sign, manage, audit.

### Changed

- **Vault Encryption** — Migrated from AES-256-CBC to AES-256-GCM (authenticated encryption).
- **Key Derivation** — Argon2id with 64MB memory, 3 iterations, 4 threads.
- **Audit Log** — SHA-256 chained, immutable, exportable for compliance.
- **Docker** — Distroless base images, multi-arch (amd64/arm64).

### Fixed

- **Bitcoin Derivation** — Fixed BIP84 vs BIP44 confusion. Now uses `m/84'/0'/0'/0/0` (Native SegWit).
- **EVM Checksum** — Enforced EIP-55 on all address outputs.
- **Rate Limiting** — Fixed burst calculation allowing 2x configured limit.

---

## Version 1.0.0 - 2026-07-01

### Added

- **Initial Release** — WalletPress Pro Self-Hosted
- **Core Vault** — AES-256-GCM encryption, Argon2id key derivation, SHA-256 chained audit log
- **REST API** — Wallet generation, management, derivation, signing
- **CLI** — Generate, derive, sign, list, delete, audit
- **WordPress Plugin (Free)** — 3 chains (Ethereum, Polygon, Base), token gating, crypto payments, wallet login
- **Chains (23)** — Bitcoin, Ethereum, Arbitrum, Optimism, Base, Polygon, BNB, Avalanche, Fantom, Gnosis, Celo, Polygon zkEVM, Linea, Mantle, Scroll, Zora, Blast, Mode, Fraxtal, Metis, Kava, Moonbeam, Moonriver

### Security

- AES-256-GCM vault encryption
- Argon2id key derivation (64MB, 3 iter, 4 threads)
- SHA-256 chained audit log
- HITL on all mutating operations
- Kill switch (`POST /api/v1/admin/vault/seal`)
- Arweave proof of generation

---

## Version 0.9.0 - 2026-04-15 (Beta)

### Added

- **Beta Release** — Core vault, REST API, CLI
- **Chains (15)** — Bitcoin, Ethereum, Arbitrum, Optimism, Base, Polygon, BNB, Avalanche, Fantom, Gnosis, Celo, Solana, Cosmos Hub, Osmosis, Polkadot
- **AES-256-GCM vault** with Argon2id key derivation
- **SHA-256 chained audit log**
- **HITL framework** (Human-In-The-Loop)
- **CLI** with table/JSON/YAML output

---

## Version 0.5.0 - 2026-01-10 (Alpha)

### Added

- **Alpha Release** — Core vault engine, basic REST API
- **Chains (8)** — Bitcoin, Ethereum, Arbitrum, Optimism, Base, Polygon, Solana, Cosmos Hub
- **Basic vault** with AES-256-GCM
- **CLI** with wallet generation

---

## Upgrade Guide

### Upgrade from v1.1.x to v1.2.0

```bash
# 1. Backup
docker exec walletpress-postgres pg_dump -U walletpress walletpress | gzip > backup-$(date +%Y%m%d).sql.gz

# 2. Pull new images
docker compose pull

# 3. Run migrations (automatic on startup)
docker compose up -d

# 4. Verify
curl http://localhost:8010/health
curl http://localhost:8010/api/v1/chains
```

**Breaking Changes:**
- `VAULT_KEY` must be regenerated if upgrading from  (Argon2id params changed)
- MCP tool names changed: `wallet_create`  ->  `generate_wallet`, `wallet_sign`  ->  `sign_transaction`
- x402 invoice format changed (added `payment_methods` array)

### Upgrade from v1.0.x to v1.1.0

```bash
# Same process, but VAULT_KEY regeneration NOT required
docker compose pull && docker compose up -d
```

**New Features Requiring Config:**
- MCP: Add `MCP_ENABLED=true` to enable
- Solana: Add Solana RPC to `SOLANA_RPC_URL`
- Cosmos: Add `COSMOS_RPC_URLS` comma-separated

---

## Release Schedule

| Version | Target Date | Focus                                                 |
| ------- | ----------- | ----------------------------------------------------- |
| 1.2.0   | 2026-11-02  | x402 v2, Arweave, 9 chains, WordPress Pro             |
| 1.3.0   | 2027-01-15  | SSO/SAML, Hardware wallet support, Advanced analytics |
| 1.4.0   | 2027-04-01  | Multi-sig, Policy engine, Compliance reporting        |
| 2.0.0   | 2027-07-01  | Plugin architecture, Marketplace, Mobile SDK          |

---

## Release Notes by Component

### Vault Engine

| Version | Changes                                           |
| ------- | ------------------------------------------------- |
| 1.2.0   | Argon2id 64MB, AES-256-GCM, SHA-256 chained audit |
| 1.1.0   | Argon2id 64MB, AES-256-GCM, SHA-256 chained audit |
| 1.0.0   | AES-256-GCM, Argon2id 64MB, SHA-256 chained audit |

### REST API

| Version | Changes                                                |
| ------- | ------------------------------------------------------ |
| 1.2.0   | x402 v2, Arweave proofs, 9 new chains, OpenAPI 3.1     |
| 1.1.0   | MCP endpoints, Solana, Cosmos, Polkadot, TRON, Ed25519 |
| 1.0.0   | Core wallet CRUD, derivation, signing                  |

### MCP Server

| Version | Changes                                                      |
| ------- | ------------------------------------------------------------ |
| 1.2.0   | 30+ tools, x402 tools, HITL improvements, framework adapters |
| 1.1.0   | Initial release, 25 tools, LangChain/CrewAI/Eliza adapters   |

### WordPress Plugin

| Version | Changes                                              |
| ------- | ---------------------------------------------------- |
| 1.2.0   | Pro: WooCommerce, Elementor, Gutenberg, 20+ webhooks |
| 1.1.0   | Free: 3 chains, token gating, payments, login        |
| 1.0.0   | Initial free release                                 |

### CLI

| Version | Changes                                             |
| ------- | --------------------------------------------------- |
| 1.2.0   | x402, vault seal/unseal, export/import, JSON output |
| 1.1.0   | Initial release, full wallet ops                    |

---

## Support Policy

| Version | Release Date | End of Support | Security Updates |
| ------- | ------------ | -------------- | ---------------- |
| 1.2.x   | 2026-11-02   | 2028-11-02     | Until 2029-11-02 |
| 1.1.x   | 2026-09-15   | 2028-09-15     | Until 2029-09-15 |
| 1.0.x   | 2026-07-01   | 2028-07-01     | Until 2029-07-01 |

---

## Contributing to Changelog

See [CONTRIBUTING.md](../development/contributing.md#changelog) for format requirements.
