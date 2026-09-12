# WalletPress — Architecture & Moving-Forward Plan

> **Status:** Canonical. Owner: WalletPress Engineering.
> **Last updated:** 2026-06-30.
> **Audience:** All engineers and agents. Read alongside AUDIT.md and SECURITY.md.
> **Purpose:** What the system is, why it is shaped that way, and where it's going.

---

## The product

**WalletPress** is an open-source (MIT) multi-chain wallet generation & management platform. The repository ships four surfaces:

| Surface | Path | Tech | Purpose |
|---------|------|------|---------|
| **Backend** | `backend/` | Python 3.12, FastAPI, SQLite | Wallet gen, vault, agent, marketplace |
| **WP plugin** | `wp-plugin/` | PHP 8, WordPress | Token gating, payments, login for WP sites |
| **Standalone MCP** | `walletpress-mcp/` | Python, FastMCP | Talk to any WalletPress backend from Claude Code / opencode / Cursor |
| **CLI** | `backend/walletpress_cli.py` | Python | Operator workflow (serve, init, generate, backup, doctor) |

Plus a marketing site (`index.html`, `buy.html`, `docs.html`, etc.) — out of scope for this doc.

---

## Architecture

### High-level

```
┌────────────────────────────────────────────────────────────────────────┐
│                          WALLETPRESS BACKEND                            │
│                                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │  HTTP API    │  │   MCP        │  │   CLI        │  │  WS Events │ │
│  │  /docs       │  │   /mcp/sse   │  │  walletpress │  │  /ws/events│ │
│  │  50+ endpoints│  │   30+ tools  │  │   9 cmds     │  │            │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘ │
│         │                 │                 │                │        │
│         ▼                 ▼                 ▼                ▼        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                      Routers + Services                          │ │
│  │   chain_vault  wallet_analysis  hosting  x402  agent_safety     │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│         │                                                              │
│         ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                          Core                                    │ │
│  │  Vault | Auth | Audit | Proof | AgentSafety | Hosting | TOTP     │ │
│  │  Email | Webhooks | License | HostingDB | EventBus | RateLimit  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│         │                                                              │
│         ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                       Wallet Engine                              │ │
│  │   generator (BIP39/32/44) | chains (55 metadata) | CHAINS.yaml  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│         │                                                              │
│         ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                       Adapters                                   │ │
│  │   langchain | crewai | eliza | openai_agents | vercel_ai         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼  (Tailscale or Tailscale+TLS via Caddy)
┌────────────────────────────────────────────────────────────────────────┐
│   OPERATOR (Talisman)                │   END USERS                      │
│   - Dashboard                       │   - WP plugin users              │
│   - x402 marketplace                │   - MCP clients                  │
│   - Backup/restore                  │   - Bot/automation devs          │
└────────────────────────────────────────────────────────────────────────┘
```

### Module map

```
backend/
├── main.py                 # FastAPI app, lifespan, middleware stack
├── x402_service.py         # Pay-per-wallet marketplace (mounted sub-app)
├── walletpress_cli.py      # CLI entrypoint
├── client_sdk.py           # Python SDK for talking to the API
│
├── core/
│   ├── config.py           # All env-driven config
│   ├── vault.py            # AES-GCM encrypted SQLite wallet store
│   ├── auth.py             # API key store + scopes
│   ├── audit.py            # Append-only JSONL audit log
│   ├── proof.py            # Merkle tree attestations + Ed25519 receipts
│   ├── agent_safety.py     # HITL, kill switch, spending limits, address book, audit chain
│   ├── hosting.py          # Hosted-mode users + Stripe stub
│   ├── rate_limit.py       # Token bucket middleware
│   ├── ip_allowlist.py     # CIDR allowlist middleware
│   ├── license.py          # JWT-signed license keys
│   ├── license_check.py    # Middleware that enforces license tier
│   ├── totp.py             # 2FA (TOTP)
│   ├── webhooks.py         # Outbound webhook delivery + retries
│   ├── email_notify.py     # SMTP notifications
│   ├── event_bus.py        # In-process pub/sub
│   ├── db_pool.py          # SQLite connection pool helper
│   ├── smart_wallet.py     # ERC-4337 smart wallet logic (754 lines — review needed)
│   ├── arweave.py          # Arweave client wrapper
│   ├── x402_verify.py      # On-chain payment verification
│   ├── x402_marketplace.py # Marketplace business logic
│   ├── pdf.py              # PDF generation (paper wallet, birth cert)
│   ├── response.py         # Response helpers
│   ├── onboarding.py       # CLI onboarding / setup wizard
│   └── proof_digest.py     # Digest / hashing helpers
│
├── wallet_engine/
│   ├── chains.py           # 55-chain registry + ChainFamily enum
│   ├── chains.yaml         # User-overridable chain config
│   └── generator.py        # BIP39/BIP32 wallet generator (594 lines)
│
├── routers/
│   ├── chain_vault.py      # Wallet CRUD + paper wallet + export (2249 lines — split)
│   ├── wallet_analysis.py  # Address scoring, risk
│   ├── wallet_memory.py    # Wallet notes / metadata
│   ├── balance_fetcher.py  # Multi-chain balance lookups
│   ├── tx_broadcaster.py   # Send tx via RPC
│   ├── test_vectors.py     # BIP39 test vector endpoint
│   ├── metrics.py          # Prometheus metrics
│   ├── airdrop.py          # CSV-driven wallet generation for airdrops
│   ├── retention.py        # Data retention policies
│   ├── health_monitor.py   # Health probes
│   ├── hosting.py          # Hosted user CRUD
│   └── license_router.py   # License key admin
│
├── agent/
│   ├── orchestrator.py     # Natural-language → plan
│   ├── mcp_server.py       # FastMCP server with 30+ tools
│   ├── scheduler.py        # Background DCA / monitor / rotate tasks
│   ├── detector.py         # Anomaly detection
│   └── providers.py        # 20 AI provider configs
│
├── adapters/               # Thin wrappers for agent frameworks (stubs)
│   ├── langchain.py
│   ├── crewai.py
│   ├── eliza.py
│   ├── openai_agents.py
│   └── vercel_ai.py
│
├── plugins/
│   ├── defi.py             # DeFi integrations + referral revenue
│   └── sdk.py              # Plugin SDK
│
├── alembic/                # Migration framework (currently unused)
└── tests/                  # 63 tests collected
```

---

## Critical user journeys

### Journey 1: User generates a wallet via WP plugin

```
WP admin → POST /wp-json/walletpress/v1/generate
   → WP plugin → backend POST /api/v1/chain-vault/wallets
      → require_auth_on_mutations (X-API-Key check)
      → chain_vault router
         → Vault.put(WalletEntry)
         → ProofOfGeneration.attest()
         → AuditTrail.log()
         → EventBus.publish("wallet.generated")
            → WebSocket broadcast → subscribers
            → Webhook delivery → subscribers
      → return {wallet_id, address, derivation_path}
   → WP plugin displays address + QR
```

**Trust assumptions:** WP plugin has a valid `walletpress_api_key`. Backend has the WP plugin's IP in `WP_ALLOWED_IPS`.

### Journey 2: AI agent executes a plan

```
User prompt: "Generate 5 SOL wallets for the airdrop"
   → MCP tool `agent_plan`
      → Orchestrator.plan_operation()
         → LLM (e.g. GPT-4o via OpenAI-compatible API)
         → Returns JSON plan: [{"tool": "wallet_generate", "args": {"chain": "sol", "count": 5}}]
   → MCP tool `agent_execute(plan, confirm=False)`
      → Orchestrator.execute_plan()
         → For each step:
            → _call_tool("wallet_generate", {...})
               → mcp_server.wallet_generate
                  → _write_with_hitl → returns confirmation_id
                  → user calls agent_confirm → executes
                     → Vault.put()
                     → ProofOfGeneration.attest()
                     → AgentSafety.audit_log() (with hash chain)
   → returns execution results
```

**Trust assumptions:** LLM doesn't go off-script. Confirmation flow is respected. Audit chain is intact.

### Journey 3: Bot pays via x402 marketplace

```
Bot → POST /api/v1/marketplace/generate
  → x402_service
     → Idempotency check (return existing order if same key)
     → Payment check:
        → credits: balance check + deduct (BROKEN: P0-1)
        → onchain: verify_payment() via Solana RPC
        → free: < MIN_ORDER_USD
     → Generate wallets (in memory)
     → Sign receipt + key-deletion attestation
     → Insert order in marketplace.db
     → Return {wallets, receipt, deletion_attestation}
```

**Trust assumptions:** Receipt signing key is private. Generated keys are not logged anywhere downstream.

### Journey 4: Operator deploys to production

```
$ walletpress deploy --domain example.com
  → check license (Pro required)
  → detect OS
  → install system deps (apt-get)
  → create /opt/walletpress + venv
  → pip install -r requirements.txt
  → generate secrets (openssl rand)
  → write /etc/walletpress/env (mode 0600)
  → install systemd unit
  → enable + start walletpress.service
  → print admin key + vault password (USER MUST SAVE)
```

**Trust assumptions:** The operator reads and saves the credentials. No one else has root on the host. Tailscale mesh is configured.

---

## Why these choices

### Why FastAPI?

- Async-native. We do a lot of I/O (RPC calls, DB queries, LLM calls).
- Auto-generated OpenAPI schema → WordPress plugin gets typed SDK.
- Pydantic validation everywhere.
- Fast iteration with `uvicorn --reload`.

### Why SQLite?

- Single-file deployment. No separate DB process to manage.
- WAL mode handles concurrent reads.
- `sqlite-vec` / FTS5 for search.
- Trade-off: no horizontal scaling. For hosted mode with >100k users, migrate to Postgres (the project already has Postgres on Talos).

### Why a separate x402 sub-app?

- The marketplace has different operational requirements (no admin key needed, no internal vault, scales independently).
- `app.mount("/", x402_app)` in main.py shares the process but the routes are isolated.
- Trade-off: shared memory = shared fate. If x402 hangs, the whole process hangs.

### Why one repo, three deliverables?

- WordPress plugin is the funnel (free).
- Backend is the engine (Pro / hosted).
- CLI is the ops surface (for Pro self-hosters).
- Same repo = atomic changes, no version drift.

### Why MCP?

- AI agents (Claude Code, opencode, Cursor) are the new ops surface.
- MCP = standard protocol. Any agent that speaks MCP can use WalletPress.
- The hosted MCP is the easiest way to give non-developers access to the wallet engine.

### Why BIP39 + BIP32?

- Industry standard. Every wallet supports it.
- Same mnemonic → same address across every tool. Users can verify against MetaMask, Phantom, Trezor.
- Determinism = trust.

---

## Moving-forward plan

The product has shipped v1.0.0-beta. Before v1.0 stable, we need to:

### Phase 0: Stabilize (this week, blocking)

Goal: No P0 or P1 bugs remain. See AUDIT.md.

| Order | Item | Owner | Estimate |
|-------|------|-------|----------|
| 1 | Disable 17 BROKEN chains (P0-4) | @engineer-1 | 1 day |
| 2 | Fix x402 credits verification (P0-1) | @engineer-2 | 0.5 day |
| 3 | Move hosted passwords to Argon2id (P0-2) | @engineer-1 | 1 day |
| 4 | Persist team keys + role enforcement (P0-3) | @engineer-2 | 1 day |
| 5 | KEK file backend (P0-5) | @engineer-1 | 2 days |
| 6 | Implement or rename wallet_sweep + DCA (P0-6 + P1-13) | @engineer-3 | 1 day |
| 7 | Audit chain mutex (P1-12) | @engineer-3 | 0.5 day |
| 8 | Receipt redaction in audit log (P1-5) | @engineer-3 | 0.5 day |
| 9 | Fix x402 verify_order DB path (P1-6) | @engineer-2 | 0.25 day |
| 10 | LLM timeout + rate limit (P1-9, P1-10, P1-11) | @engineer-3 | 1 day |
| 11 | Fix _verify saves on read (P1-1) | @engineer-2 | 0.5 day |
| 12 | Audit trail integrity (P1-4) | @engineer-2 | 1 day |

**Total: ~10 engineer-days.** Cut `v1.0.0-audit` after this phase.

### Phase 1: Fix the 17 broken chains (this sprint)

Per-chain work. Each chain needs:
- Reference SDK installed in dev requirements
- `tests/test_address_vectors.py` golden-vector test
- Implementation in `wallet_engine/generator.py` (or a new per-chain module)
- Update `chains.py` to remove `generation_disabled`
- Update `ADDRESS_GENERATION.md`

Priority order (highest user demand first):
1. **Stellar** (`xlm`) — 30 min, use `stellar-sdk`
2. **Tezos** (`xtz`) — 1 hour, use `pytezos`
3. **Injective** (`inj`) — 1 hour, bech32 + ETH path
4. **Cosmos Hub** (`atom`) — 1 hour, bech32
5. **Osmosis / Sei / Juno / Evmos** — 2 hours each, same pattern
6. **Algorand** (`algo`) — 1 hour, base32 + checksum
7. **TON** (`ton`) — 2 hours, custom format
8. **Filecoin** (`fil`) — 1 hour, blake2b
9. **Nano** (`xno`) — 1 hour, base32 + blake2b
10. **Polkadot / Kusama** — 4 hours, sr25519 (use `substrate-interface`)
11. **Monero** (`xmr`) — 6 hours, custom Monero crypto
12. **Cardano** (`ada`) — 8 hours, Bech32 stake/enterprise
13. **Bitcoin Cash** (`bch`) — 1 hour, cashaddr
14. **XRP** (`xrp`) — 2 hours, custom base58 alphabet
15. **Zcash** (`zec`) — 1 hour, prefix fix

**Total: ~25 engineer-days.** Cut `v1.1.0` after this phase.

### Phase 2: Architectural cleanup (next sprint)

| Item | Why | Estimate |
|------|-----|----------|
| Split `chain_vault.py` (2249 lines) into 4 modules | Maintainability | 2 days |
| Migrate raw SQL → Alembic | Schema migrations | 3 days |
| Consolidate DB paths to one `walletpress.db` | Operations | 1 day |
| Pluggable KeyBackend (env / file / KMS) | P0-5 follow-on | 3 days |
| Per-wallet derived keys (HKDF) | Revocation granularity | 2 days |
| Pydantic models for all MCP tool args | Type safety | 2 days |
| Repository pattern for SQLite stores | Testability | 3 days |
| Replace JSON `KeyStore` + `TeamKeyStore` with SQLite | Persistence | 1 day |

**Total: ~17 engineer-days.** Cut `v1.2.0` after this phase.

### Phase 3: Ship the roadmap (next month)

From ROADMAP.md (now validated against actual code gaps):

| Item | From | Status | Notes |
|------|------|--------|-------|
| #1 Paper wallet PDF | ROADMAP | already exists (`core/pdf.py`) | Verify output |
| #2 SSE progress for batch | ROADMAP | not built | High impact |
| #3 Mnemonic auto-detect chain | ROADMAP | not built | After phase 1 |
| #4 QR codes on addresses | ROADMAP | already built (`?include_qr=true`) | Verify |
| #5 Webhook delivery log + retry | ROADMAP | partial | `webhooks.py` has retries but no UI |
| #6 Per-API-key rate limit | ROADMAP | partial | Falls back to IP — fix |
| #7 Backup + restore CLI | ROADMAP | partial — doesn't encrypt | Add encryption |
| #8 Clean error messages | ROADMAP | partial | Audit each router |
| #9 Temporal wallet cleanup | ROADMAP | built (`temporal_cleanup_loop`) | Verify |
| #10 Full-text search | ROADMAP | built (FTS5) | Verify |
| #11 Email verification | ROADMAP | **not built** | High priority for hosted |
| #12 Login rate limit | ROADMAP | **not built** | High priority |
| #13 Birth certificate PDF | ROADMAP | already built (`core/pdf.py`) | Verify |
| #14 Chain auto-detect on import | ROADMAP | not built | After phase 1 |
| #15 Signed webhook payloads | ROADMAP | already built (HMAC-SHA-256) | Verify |

**Real outstanding: SSE batch, email verification, login rate limit, encrypted backup, chain auto-detect.**

### Phase 4: Operational maturity (month 2)

- Off-site backup replication (Hydra mirror, daily)
- Monitoring + alerting (Loki + GlitchTip + Grafana)
- Load testing (Locust)
- Penetration test (external)
- SBOM + Sigstore for Docker images
- GDPR data export + delete endpoints for hosted

### Phase 5: Desktop + Mobile (month 3+)

From STRATEGY.md:
- **Tauri desktop app** (offline-capable, bundled backend)
- **PWA / React Native** (mobile wallet generator)

These are separate product surfaces. Defer until v1.2.0 ships.

---

## What we are NOT building

To keep the team focused, we're explicitly saying no to:

1. **Browser-extension wallet.** Too much surface area for security bugs. MetaMask owns this. WP plugin + MCP is enough.
2. **On-chain transaction broadcasting as a feature for self-hosted.** Tx broadcasting requires custody decisions and MEV protection. Pro users get signing only. Hosted gets delegated through Stripe KYC'd accounts.
3. **In-app DEX / swap.** Too many chains, too many MEV risks, too much regulatory exposure. The referral kickback via `plugins/defi.py` is enough.
4. **Multi-sig / threshold sig.** Complex. High error rate. Trezor/Ledger own this.
5. **Hardware wallet integration.** Ledger/Trezor already cover this. We're the software layer on top.

---

## Non-goals (for v1.x)

- ICO / token launch tooling
- NFT minting
- DAO tooling
- Web3 identity (DID / verifiable credentials)
- Decentralized storage integration
- Browser extension

---

## Open architectural questions

Need product-side decisions before we build:

1. **Hosted vs self-hosted split.** Today both share a codebase. Should hosted be a fork?
   - Pro: cleaner boundary, fewer env vars
   - Con: double maintenance burden
   - Recommendation: shared codebase, but `if cfg.hosted:` branches in the right places.

2. **MCP as the only AI surface, or also LangChain/CrewAI/Eliza adapters?**
   - The adapters are stubs today. Either implement or remove.
   - Recommendation: implement only MCP. It's the standard. The others can wrap MCP if needed.

3. **WordPress plugin strategy.**
   - The plugin is GPL by WordPress convention. Backend is MIT.
   - Recommendation: keep plugin separate, MIT-licensed too. Some users fork.

4. **Postgres migration for hosted mode.**
   - SQLite + WAL handles ~100 concurrent users.
   - Beyond that, need Postgres.
   - Recommendation: phase this when we hit 1000 paid users.

5. **Lightweight Postgres-only deployment.**
   - Skip SQLite, always Postgres.
   - Recommendation: out of scope for v1. SQLite is part of the value prop.

---

## Cross-product consistency

WalletPress is one of three Rug Munch Media products. To avoid duplicate implementations:

| Concern | WalletPress | RMI | Pry |
|---------|-------------|-----|-----|
| Multi-tenant user mgmt | `core/hosting.py` | (RMI uses Talos Postgres auth) | (Pry is single-tenant) |
| API key store | `core/auth.py` | (RMI uses HTTP-only sessions) | (Pry uses env) |
| Audit trail | `core/audit.py` (JSONL) | RMI `app/audit/` (Postgres) | (Pry logs to stderr) |
| RPC pool | hardcoded list in `chains.py` | `app/databus/` (52 files) | per-job RPC |
| Provider pattern | `agent/providers.py` (20 AI providers) | `app/scanners/shared.py` | per-job |

**Decision:** Each product owns its own. Sharing via a `rugmunch-common` package is rejected — over-engineering for three products. Copy-paste OK if it keeps the products independent.

---

## See also

- `AUDIT.md` — bugs and fixes (priority-ordered)
- `SECURITY.md` — threat model, auth, crypto rules
- `ADDRESS_GENERATION.md` — per-chain truth table
- `BUILDER.md` — daily workflow for agents
- `WALLETPRESS.md` — single-paragraph product summary
