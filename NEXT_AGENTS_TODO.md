# WalletPress — Next Agents TODO

> **Created:** 2026-09-02 · **Author:** Lead Agent (GLM-5.2 audit session)
> **Supersedes:** TODO.md (2026-07-31) — that file's findings are merged below
> **Status:** NOT SAFE FOR FUNDS. 8 critical vulns + 7 wins done. 43 wins remaining.

## Quick Start for Next Fleet

1. `cd /srv/work/repos/walletpress`
2. Read this file top-to-bottom. It's your full task list.
3. Check `git status` — there are UNCOMMITTED changes from the last session (wins 1-7). Commit them first OR build on top.
4. Run `cd backend && pytest tests/ -v --tb=short` — expect 515 pass, 5 fail (all pre-existing, see below).
5. Pick wins from the NEXT section. 3 agents max in parallel. Disjoint file sets only.

---

## DONE — Wins 1-7 (this session, UNCOMMITTED)

| # | Win | Files touched | Agent |
|---|-----|---------------|-------|
| 1 | Sui address derivation fixed (SHA3-256) | chain_addresses.py, generator.py | GLM-5.3 #1 |
| 2 | Aptos address derivation fixed (SHA3-256, flag appended) | chain_addresses.py, generator.py | GLM-5.3 #1 |
| 3 | NEAR address derivation fixed (ed25519:base58) | chain_addresses.py, generator.py | GLM-5.3 #1 |
| 4 | Polkadot/Kusama now sr25519 (substrate-interface) | chain_addresses.py, generator.py | GLM-5.3 #1 |
| 5 | 7 crypto deps pinned exact + requirements.lock with hashes | pyproject.toml, requirements.txt, requirements.lock | GLM-5.3 #2 |
| 6 | ecdsa removed from deps (was never imported) | pyproject.toml, requirements.txt | GLM-5.3 #2 |
| 7 | Constant-time comparison (hmac.compare_digest) + receipt key TOCTOU + KEK wrapping + vault put() ALTER removed | proof.py, agent_safety.py, vault.py | GLM-5.3 #3 |

**Bonus fixes found during work:**
- Dead-code address branches removed from `_generate_ed25519` (now raises loudly)
- Nano chain key mismatch fixed (`xno` vs `nano` — was silently producing wrong addresses)
- `_generate_ss58` removed (was deriving ed25519 for sr25519 chains)
- `argon2-cffi` and `pycryptodomex` added as explicit pinned deps

**Test status:** 515 passed, 5 failed (ALL pre-existing), 5 skipped. Zero regressions.

**Pre-existing failures (NOT caused by this session):**
- 3x Cardano tests — `pycardano`↔`cbor2` version incompatibility in env
- test_all_chains_generate_valid_wallet — same Cardano cascade
- test_aptos_address_matches_aptos_sdk — `aptos-sdk` can't pip-install (PEP 668 system Python)

**Agent flags (need decisions):**
- ecdsa remains as transitive dep of bip-utils (hash-pinned in lockfile). Full removal = fork bip-utils.
- Aptos golden vector test needs aptos-sdk in CI Docker image (not system Python).
- Existing deployments with plaintext receipt key keep working (legacy path) but stay plaintext until file deleted + regenerated.

---

## NEXT — Wins 8-50, prioritized by funds-loss risk

### Phase A — BLOCKING SECURITY (8 items, ~5 days, funds-loss risk)

> These are from the July 31 audit (TODO.md). They are the REAL production blockers.
> My Sep 2 audit focused on crypto correctness; these are access-control holes.

| # | Win | Files | Risk | Effort |
|---|-----|-------|------|--------|
| 8 | **Gate /mcp behind API-key auth** — main.py:266 exempts /mcp/ from auth. MCP can decrypt keys, sweep wallets. Attacker self-approves via agent_confirm. | main.py, mcp_server.py | CRITICAL | 0.5d |
| 9 | **Fix spending-limit bypass** — mcp_server.py:771 calls check_spending_limit(chain, 0). Entire wallet sweep validated as 0-amount. | mcp_server.py, agent_safety.py | CRITICAL | 0.5d |
| 10 | **Enforce auth on ALL GET endpoints** — require_auth_on_mutations only blocks writes. Every GET on vault/retention is public: addresses, labels, balances exposed. | main.py, chain_vault.py, routers/* | CRITICAL | 1d |
| 11 | **Fix scope injection** — chain_vault.py:478-486: operator can mint API key with scopes=["admin"] → full key export. Validate server-side. | chain_vault.py, auth.py | CRITICAL | 0.5d |
| 12 | **Fix x402 free key dispenser** — MIN_ORDER_USD=1.00, PRICE_PER_WALLET=0.01 → 99 free wallets with plaintext keys. Credits accepts any string. | x402_service.py | CRITICAL | 0.5d |
| 13 | **Fix timelock execution** — smart_wallet.py:682-743: sends encrypted key blob as raw tx, fakes tx hashes. Implement real decrypt→build→sign→broadcast. | smart_wallet.py | CRITICAL | 1d |
| 14 | **Fix social recovery** — smart_wallet.py:295-306: claimant sig always True for any non-empty sig. Guardian sigs not bound to message (replay). EVM uses SHA-256 not EIP-191. | smart_wallet.py | CRITICAL | 1d |
| 15 | **Fix wp-plugin login bypass** — unconfigured plugin skips sig verification. Configured path calls stub endpoint returning verified:False which PHP treats as success. | wp-plugin/includes/class-walletpress.php | CRITICAL | 0.5d |

### Phase B — HIGH SECURITY (10 items, ~5 days)

| # | Win | Files | Effort |
|---|-----|-------|--------|
| 16 | Fix plaintext key storage on import — chain_vault.py:240: when WP_VAULT_PASSWORD unset, keys stored plaintext. Fail closed. | chain_vault.py | 0.5d |
| 17 | Fix airdrop key loss — routers/airdrop.py: generates wallets with no vault password → keys permanently discarded. | routers/airdrop.py | 0.5d |
| 18 | Fix /derive-address mnemonic oracle — chain_vault.py:501-523: echoes user mnemonic, derives for any operator. | chain_vault.py | 0.25d |
| 19 | Fix /vault/{id}/full encrypted blob mislabel — chain_vault.py:401: private_key_hex contains base64 ciphertext, not decrypted key. | chain_vault.py | 0.25d |
| 20 | Fix webhook secret exposure + SSRF — returns secrets to any authed user; DNS rebinding bypass. | core/webhooks.py | 0.5d |
| 21 | Fix JWT algorithm confusion — jwt_auth.py:111: HS256 with public RSA key as HMAC secret → token forgery. | core/jwt_auth.py | 0.5d |
| 22 | Fix license admin key in query param — travels in URL → access logs, browser history. | routers/license_router.py | 0.25d |
| 23 | Fix free plan self-upgrade — routers/hosting.py: any free user can POST plan="enterprise". | routers/hosting.py | 0.25d |
| 24 | Fix admin key not validated — only checks non-empty. .env.example ships "change-me-to-a-random-string". | core/config.py, .env.example | 0.25d |
| 25 | Enforce HTTPS for key-returning endpoints + add HSTS header. | main.py, x402_service.py | 0.5d |

### Phase C — MEDIUM SECURITY + WP PLUGIN (5 items, ~2 days)

| # | Win | Files | Effort |
|---|-----|-------|--------|
| 26 | Replace WP plugin AES-CBC with AES-GCM (P2-18) — wp-plugin uses aes-256-cbc without HMAC, malleable. | wp-plugin/includes/class-walletpress.php | 0.5d |
| 27 | Add per-API-key rate limiting (not just IP-based) — hosted mode shares IPs. | core/rate_limit.py, main.py | 0.5d |
| 28 | Add login rate limiting + email verification — routers/hosting.py has no rate limit, no email verify. | routers/hosting.py, core/hosting.py | 1d |
| 29 | Zero-out vault password after init (P2-7) — core/config.py reads at class def time, never clears. | core/config.py, main.py | 0.25d |
| 30 | Fix audit log NOT hash-chained — SECURITY.md claims SHA-256 chain; actual is plain JSONL. Implement or update docs. | core/audit.py | 0.5d |

### Phase D — WALLET ENGINE REMAINING (5 items, ~3 days)

| # | Win | Files | Effort |
|---|-----|-------|--------|
| 31 | Add address golden-vector tests for ALL 38+ working chains — each test: known mnemonic → compare vs reference SDK. | tests/test_address_vectors.py | 2d |
| 32 | Add import_from_private_key address derivation for all ed25519 chains — currently only sol gets real address, rest get "imported:{chain}" placeholder. | generator.py | 1d |
| 33 | Consolidate chains.py truth with ADDRESS_GENERATION.md — remove 5 dead enum values (CASPER, ELROND, HEDERA, INTERNET_COMPUTER, ZILLIQA). | chains.py, ADDRESS_GENERATION.md | 0.5d |
| 34 | Remove dead WP plugin supported_chains() entries — advertises manta, starknet, polygon_zkevm, hedera, elrond, casper, zilliqa (backend has none). | wp-plugin/includes/class-walletpress.php | 0.25d |
| 35 | Add --dry-run + --count to CLI generate (P3-14, P3-15) + EIP-55 checksum validation (P3-15). | walletpress_cli.py | 0.5d |

### Phase E — AI AGENT SAFETY (5 items, ~3 days)

| # | Win | Files | Effort |
|---|-----|-------|--------|
| 36 | Fix HITL bypass in orchestrator plan execution (P1-10) — verify execute_plan checks WRITE_ACTIONS before each step. | agent/orchestrator.py | 0.5d |
| 37 | Add JSON-schema validation to agent plans (P1-11) — allowlist tool names, reject unknown, require HITL for WRITE, default sandbox_dry_run=True. | agent/orchestrator.py | 0.5d |
| 38 | Add LLM call timeout + per-key rate limit (P1-9) — no timeout on chat.completions.create(), one hung request blocks a worker. | agent/orchestrator.py, mcp_server.py | 0.5d |
| 39 | Add mnemonic redaction to ALL audit log paths (P1-5) — regex filter stripping 12/24-word BIP39 patterns from ALL audit params. | agent_safety.py, mcp_server.py | 0.5d |
| 40 | Split agent_safety.py (893 lines) into hitl.py, spending.py, address_book.py, kill_switch.py, audit_chain.py. | core/agent_safety.py → core/agent_safety/ | 1d |

### Phase F — TESTING (5 items, ~3 days)

| # | Win | Files | Effort |
|---|-----|-------|--------|
| 41 | Add coverage gate to CI + measure security-path coverage — pytest --cov --cov-fail-under=70. vault/generator/agent_safety/proof/auth must be ≥90%. | .forgejo/workflows/ci.yml, pyproject.toml | 0.5d |
| 42 | Add adversarial/mutation tests — mutmut on generator.py, vault.py, proof.py, agent_safety.py. Crucible adversarial pass per AI Test Oracle Policy. | tests/ | 1d |
| 43 | Add concurrent-write tests for vault — 50 threads doing put()+get() simultaneously, verify integrity. | tests/test_vault_concurrent.py | 0.5d |
| 44 | Add property-based tests (Hypothesis) — any valid mnemonic → same address (determinism) + matches reference (correctness). | tests/ | 0.5d |
| 45 | Add test verifying NO mnemonic/private key in any log or DB after full test run. | tests/test_no_secret_leak.py | 0.5d |

### Phase G — CI/CD (5 items, ~2 days)

| # | Win | Files | Effort |
|---|-----|-------|--------|
| 46 | Add mypy strict + bandit + gitleaks to CI (not just Makefile). Fix 93 ruff errors first (P3-1). | .forgejo/workflows/ci.yml | 1d |
| 47 | Add Docker lint (hadolint) + container scan (Trivy) + SBOM (Syft) + image signing (cosign). | .forgejo/workflows/ci.yml, Dockerfile | 0.5d |
| 48 | Fix CI test path — pytest tests/ but tests live in backend/tests/. Current CI collects nothing. | .forgejo/workflows/ci.yml | 0.25d |
| 49 | Add k6 load test smoke (10 VUs, 30s) — nightly job, p95 < 200ms reads, < 500ms generation. | .forgejo/workflows/ci.yml | 0.5d |
| 50 | Add pip-audit weekly + Renovate config validation. | .forgejo/workflows/ci.yml, renovate.json | 0.25d |

### Phase H — ARCHITECTURE (not blocking production but needed for A+)

| # | Win | Files | Effort |
|---|-----|-------|--------|
| H1 | Consolidate 4 SQLite DBs → 1 walletpress.db with namespaced tables. Use Alembic for all schema. | core/*.py, alembic/ | 2d |
| H2 | Split main.py (946 lines) → app.py, middleware.py, ws.py, team_keys.py. Review smart_wallet.py (795 lines). | main.py | 1d |
| H3 | Replace JSON/dict stores with SQLite + Pydantic models (KeyStore, TeamKeyStore, ScheduledTask, scam_addresses.json). | core/*.py | 1d |
| H4 | Remove 5 adapter stubs (P3-11) — langchain, crewai, eliza, openai_agents, vercel_ai are 16-36 line placeholders. | adapters/ | 0.25d |
| H5 | Update STATUS.md + AUDIT.md to reflect reality. AUDIT.md claims "all P1s fixed" but P1-3 was still live. | STATUS.md, AUDIT.md | 0.5d |
| H6 | Add walletpress doctor command — self-checks: vault encryption, KEK file perms, chain SDKs, test vectors, audit chain, receipt key. | walletpress_cli.py | 0.5d |
| H7 | Fix GeneratedWallet.clear_sensitive() no-op — zeroes fields that are always None. Secrets never cleared from memory. | generator.py | 0.25d |
| H8 | Fix vault.put returns bool but errors swallowed — silent write failures. | vault.py | 0.25d |
| H9 | Fix partial-generation on failure — persists wallets mid-loop then 500s, no rollback. | mcp_server.py, chain_vault.py | 0.5d |
| H10 | Fix DCA scheduler sweeps entire balance — ignores task.amount, drains wallet. | agent/scheduler.py | 0.5d |

---

## Parallel Agent Assignment Guide

**Rules for 3-agent parallel dispatch:**
- Each agent gets a DISJOINT file set (no shared files).
- One agent per phase subsection (A, B, C...) to avoid file overlap.
- Agent verifies with `pytest` before returning.
- Agent reports `[REVIEW]` flags on uncertainty.

**Recommended batch 1 (Phase A — CRITICAL):**
- Agent 1: main.py + mcp_server.py (wins 8, 9)
- Agent 2: chain_vault.py + auth.py + x402_service.py (wins 10, 11, 12)
- Agent 3: smart_wallet.py + wp-plugin/ (wins 13, 14, 15)

**Recommended batch 2 (Phase B — HIGH):**
- Agent 1: chain_vault.py + routers/airdrop.py (wins 16, 17, 18, 19)
- Agent 2: core/webhooks.py + jwt_auth.py + license_router.py (wins 20, 21, 22)
- Agent 3: routers/hosting.py + core/config.py + main.py (wins 23, 24, 25)

**Recommended batch 3 (Phase C+D — MEDIUM + ENGINE):**
- Agent 1: wp-plugin/ + core/rate_limit.py + core/hosting.py + core/audit.py (wins 26-30)
- Agent 2: tests/test_address_vectors.py + generator.py (wins 31, 32)
- Agent 3: chains.py + walletpress_cli.py + wp-plugin/ (wins 33, 34, 35)

**Recommended batch 4 (Phase E+F — AGENT + TESTING):**
- Agent 1: agent/orchestrator.py + agent_safety.py (wins 36-40)
- Agent 2: tests/ new files (wins 42-45)
- Agent 3: .forgejo/workflows/ci.yml + pyproject.toml (wins 41, 46-50)

**Recommended batch 5 (Phase G+H — CI + ARCH):**
- 2-3 agents on disjoint file sets per the table above.

---

## Repo State

- **Branch:** main
- **Last commit:** b5aa8aa (security(auth): verify signature VERDICT)
- **Working tree:** 9 files modified (uncommitted — wins 1-7)
- **Codebase:** 102 Python files, 25,560 lines
- **Tests:** 24 test files, 515 pass / 5 fail (pre-existing) / 5 skip
- **Prior audits:** AUDIT.md (June 30 — P0/P1 claims, some FALSE), TODO.md (July 31 — 8 CRITICAL vulns)
- **Knowledge graph:** indexed (2,942 nodes, 11,385 edges) — use `codebase-memory-mcp` with project="walletpress"

## Key Files Reference

| File | Lines | Role | Critical? |
|------|-------|------|-----------|
| backend/main.py | 946 | FastAPI app, lifespan, middleware, auth, WS, team keys | YES |
| backend/core/vault.py | 386 | AES-GCM encrypted wallet store | YES |
| backend/core/agent_safety.py | 893 | HITL, spending limits, kill switch, audit chain | YES |
| backend/core/proof.py | ~800 | Merkle attestations, Ed25519 receipts | YES |
| backend/core/smart_wallet.py | 795 | ERC-4337 smart wallet, timelock, social recovery | YES |
| backend/wallet_engine/generator.py | 1002 | BIP39/32/44 wallet generator, 55 chains | YES |
| backend/wallet_engine/chain_addresses.py | ~450 | Per-chain address encoders | YES |
| backend/agent/mcp_server.py | 146→? | FastMCP server, 30+ tools | YES |
| backend/agent/orchestrator.py | ~200 | NL→plan→execute, LLM calls | YES |
| backend/routers/chain_vault.py | 529 | Wallet CRUD, import, export, paper wallet | YES |
| backend/x402_service.py | 330 | Pay-per-wallet marketplace | YES |
| backend/core/hosting.py | ~110 | Hosted users, registration, login | YES |
| wp-plugin/includes/class-walletpress.php | ~200 | WP plugin: token gating, payments, login | YES |

## Total Effort Estimate

| Phase | Wins | Days |
|-------|------|------|
| DONE (this session) | 1-7 | 0 |
| A — Blocking security | 8-15 | 5 |
| B — High security | 16-25 | 5 |
| C — Medium security | 26-30 | 2 |
| D — Wallet engine | 31-35 | 3 |
| E — Agent safety | 36-40 | 3 |
| F — Testing | 41-45 | 3 |
| G — CI/CD | 46-50 | 2 |
| H — Architecture | H1-H10 | 5 |
| **Total remaining** | **43 wins** | **~28 days** |

**Production-safe milestone:** After Phase A + B (wins 8-25) = ~10 days. Then external pen-test before any user funds.
