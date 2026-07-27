# WalletPress — Daily Builder Workflow

> **Status:** Canonical. Owner: WalletPress Engineering.
> **Last updated:** 2026-06-30.
> **Audience:** Every AI agent and engineer working on WalletPress. Read on session start.
> **Purpose:** The single workflow every contributor follows so nothing gets duplicated, every change has context, and the repo stays coherent day over day.

---

## TL;DR — Read this first

Every session, every agent, every engineer:

1. **Read the four canonical docs in order:** WALLETPRESS.md → ARCHITECTURE.md → SECURITY.md → AUDIT.md.
2. **Pick from the open work list** below. Don't pick from scratch — the list is the canonical "what's next."
3. **Touch only what's assigned.** If you find a related bug, log it in AUDIT.md "Known issues" and move on. Don't fix it in this PR.
4. **One logical change per PR.** Conventional commits. Tests in the same PR.
5. **Push daily** (`git push origin main`). Multi-remote mirroring via script.
6. **Update the docs in the same PR** if you change behavior. Docs drift is the #1 cause of agent misalignment.

---

## Source-of-truth hierarchy

If two files disagree, trust in this order:

1. **The code itself** — `git log` to see intent.
2. **AUDIT.md** — bugs and known issues.
3. **ARCHITECTURE.md** — design + roadmap.
4. **SECURITY.md** — security rules.
5. **ADDRESS_GENERATION.md** — chain truth table.
6. **BUILDER.md** (this file) — workflow.
7. **WALLETPRESS.md** — product summary.
8. **STRATEGY.md** — business plan (lowest priority — most stale).
9. **PROGRESS.md / ROADMAP.md / ROADMAP_V2.md** — historical. Aspirational. Don't trust claims; check the code.

If you find a conflict between source-of-truth files, raise it in the daily standup. Don't silently pick one.

---

## Session-start checklist (every agent, every time)

Before writing any code:

```bash
# 1. Update the working tree
cd ~/sites/walletpress
git fetch --all
git status
git log --oneline -10

# 2. Run the audit
cd backend
make check    # lint + type + test
make security # bandit + safety

# 3. Verify environment
echo "WP_ADMIN_KEY set: $([ -n "$WP_ADMIN_KEY" ] && echo yes || echo NO)"
echo "WP_VAULT_PASSWORD set: $([ -n "$WP_VAULT_PASSWORD" ] && echo yes || echo NO)"
which uvicorn
python3 -c "import bip_utils, cryptography, ecdsa, pynacl, coincurve; print('crypto deps OK')"

# 4. Read today's standup notes (if maintained)
cat docs/standup/$(date +%Y-%m-%d).md 2>/dev/null || echo "No standup yet today"
```

If any of these fail, do not start a new feature — fix the break first.

---

## The "what's next" list

This is the canonical work queue. Items have stable IDs (`WP-NNN`) so they can be referenced across docs and PRs.

### WP-001 → WP-020 — P0 from AUDIT.md (do FIRST)

| ID | Item | Owner | Status |
|----|------|-------|--------|
| WP-001 | Disable 17 BROKEN chains in chains.py | — | **DONE** (2026-06-30) — all 17 chains fixed via chain_addresses module instead of disabled |
| WP-002 | Fix x402 credits verification (no payment = no credit) | — | **DONE** (2026-06-30) — verify_payment() called before crediting |
| WP-003 | Migrate hosted passwords to Argon2id | — | **DONE** (2026-06-30) — argon2-cffi PasswordHasher, legacy SHA-256 migrates on login |
| WP-004 | Persist team keys + role enforcement | — | **DONE** (2026-06-30) — KeyStore has role field, middleware enforces operator min on writes |
| WP-005 | KEK file backend (replace env-only vault password) | — | **DONE** (2026-06-30) — file > env, auto-generates on first run, mode 0600 |
| WP-006 | Implement or rename `wallet_sweep` and DCA scheduler | — | **DONE** (2026-06-30) — EVM chains broadcast via Web3 + eth_account; non-EVM still intent |

### WP-021 → WP-040 — P1 from AUDIT.md

| ID | Item | Owner | Status |
|----|------|-------|--------|
| WP-021 | `verify()` writes on every read (perf + race) | — | open |
| WP-022 | Add real Alembic migrations (currently dead code) | — | open |
| WP-023 | Remove ALTER-on-every-put in vault.py | — | open |
| WP-024 | Audit log integrity chain (SHA-256 like agent_safety) | — | open |
| WP-025 | Redact mnemonic from audit log | — | open |
| WP-026 | Fix x402 verify_order DB path | — | open |
| WP-027 | x402 keys-in-body opt-in flag | — | open |
| WP-028 | x402 xpub derivation correct address format per chain | — | open |
| WP-029 | LLM call timeout + per-key rate limit | — | open |
| WP-030 | Orchestrator HITL bypass fix | — | open |
| WP-031 | Plan JSON schema validation (anti-prompt-injection) | — | open |
| WP-032 | audit_log hash chain mutex | — | open |
| WP-033 | DCA scheduler actually executes | — | open |
| WP-034 | Receipt signing key envelope encryption | — | open |

### WP-040 → WP-060 — Phase 1 broken chains (per-chain work)

| ID | Chain | Effort | Status |
|----|-------|--------|--------|
| WP-040 | Stellar (xlm) | S | **DONE** (2026-06-30) — stellar-sdk verified |
| WP-041 | Tezos (xtz) | S | **DONE** (2026-06-30) — manual tz1 watermark impl |
| WP-042 | Injective (inj) | S | **DONE** (2026-06-30) — bech32 with HRP |
| WP-043 | Cosmos Hub (atom) | S | **DONE** (2026-06-30) — bech32 with HRP |
| WP-044 | Osmosis (osmo) | S | **DONE** (2026-06-30) — bech32 with HRP |
| WP-045 | Sei (sei) | S | **DONE** (2026-06-30) — bech32 with HRP |
| WP-046 | Juno (juno) | S | **DONE** (2026-06-30) — bech32 with HRP |
| WP-047 | Evmos (evmos) | S | **DONE** (2026-06-30) — bech32 with HRP |
| WP-048 | Algorand (algo) | S | **DONE** (2026-06-30) — SHA-512/256 checksum |
| WP-049 | TON | M | **DONE** (2026-06-30) — manual workchain+CRC16 impl |
| WP-050 | Filecoin (fil) | S | **DONE** (2026-06-30) — f1 + blake2b impl |
| WP-051 | Nano (xno) | S | **DONE** (2026-06-30) — manual blake2b impl |
| WP-052 | Polkadot (dot) — sr25519 | L | **DONE** (2026-06-30) — substrate-interface |
| WP-053 | Kusama (ksm) — sr25519 | L | **DONE** (2026-06-30) — substrate-interface |
| WP-054 | Monero (xmr) | L | **DONE** (2026-06-30) — monero library |
| WP-055 | Cardano (ada) — Bech32 stake | L | **DONE** (2026-06-30) — pycardano Kholaw + verified against cardano-address CLI |
| WP-056 | Bitcoin Cash (bch) — cashaddr | S | **DONE** (2026-06-30) — bitcash |
| WP-057 | XRP — custom alphabet | M | **DONE** (2026-06-30) — manual XRP alphabet impl |
| WP-058 | Zcash (zec) — prefix fix | S | **DONE** (2026-06-30) — 0x1C → 0x1CB8 |
| WP-059 | BTC segwit variants | M | open |

### WP-060 → WP-080 — Phase 2 architectural cleanup

| ID | Item | Status |
|----|------|--------|
| WP-060 | Split `chain_vault.py` (2249 lines) into 4 modules | open |
| WP-061 | Migrate raw SQL → Alembic | open |
| WP-062 | Consolidate DB paths | open |
| WP-063 | Pluggable KeyBackend | open |
| WP-064 | Per-wallet HKDF keys | open |
| WP-065 | Pydantic MCP tool args | open |
| WP-066 | Repository pattern | open |
| WP-067 | Replace JSON KeyStore with SQLite | open |

### WP-080 → WP-100 — Phase 3 product features

| ID | Item | Status |
|----|------|--------|
| WP-080 | SSE progress for batch generation | open |
| WP-081 | Email verification (hosted) | open |
| WP-082 | Login rate limit (hosted) | open |
| WP-083 | Encrypted backup archive | open |
| WP-084 | Chain auto-detect on mnemonic import | open |
| WP-085 | Off-site backup replication | open |
| WP-086 | Monitoring + alerting | open |
| WP-087 | Load testing (Locust) | open |
| WP-088 | External pen test | open |
| WP-089 | SBOM + Sigstore for Docker images | open |
| WP-090 | GDPR data export + delete (hosted) | open |

### WP-100 → WP-120 — Phase 4 desktop + mobile

| ID | Item | Status |
|----|------|--------|
| WP-100 | Tauri desktop app | open |
| WP-101 | PWA mobile | open |
| WP-102 | React Native app | open |

---

## PR / commit workflow

### Branching

- `main` — always green. Never commit broken code.
- `feat/WP-NNN-short-name` — feature branch.
- `fix/WP-NNN-short-name` — bug fix branch.
- `chore/*` — maintenance.

### Commit messages

Conventional commits. Mandatory.

```
feat(wallet_engine): add bech32 Cosmos address generation

Closes WP-043.

- Use bech32 library with HRP per chain
- Verified against cosmjs reference for 4 test mnemonics
- tests/test_address_vectors.py updated

Refs: ADDRESS_GENERATION.md
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `security`.

### PR template

`.github/pull_request_template.md` should include:

```markdown
## Summary
[1-2 sentences]

## WP ID
[WP-NNN from BUILDER.md]

## Source-of-truth docs updated
- [ ] AUDIT.md (if bug fix)
- [ ] ADDRESS_GENERATION.md (if chain change)
- [ ] ARCHITECTURE.md (if architectural change)
- [ ] SECURITY.md (if security change)

## Checklist
- [ ] `make check` passes locally
- [ ] `make security` passes
- [ ] Test added for new behavior
- [ ] No P0/P1 bugs introduced
- [ ] No secrets in diff
- [ ] Conventional commit message

## How to verify
[Specific commands an agent can run to confirm]
```

### What NOT to do in a PR

1. **Don't bundle unrelated changes.** One logical change per PR.
2. **Don't refactor while fixing.** That's two PRs.
3. **Don't update PROGRESS.md / ROADMAP.md** unless you're explicitly rewriting those docs.
4. **Don't add dependencies** without a justification paragraph in the PR body.
5. **Don't change the public API** without updating the WP plugin or SDK in the same PR.
6. **Don't add new chains** without ADDRESS_GENERATION.md update + tests.

---

## Daily standup format

`docs/standup/YYYY-MM-DD.md`:

```markdown
# Standup — YYYY-MM-DD

## Yesterday
- @engineer-1: WP-003 migrated 12 of 47 hosted users to Argon2id
- @engineer-2: WP-040 Stellar address gen + test passing
- @engineer-3: WP-006 decided on "implement" — opened sub-tasks

## Today
- @engineer-1: WP-003 migration script ready for review (PR #123)
- @engineer-2: WP-041 Tezos start
- @engineer-3: WP-006 sweep implementation draft

## Blockers
- WP-001 needs product decision: do we ship with 17 chains disabled, or block release on fixing them all?

## Decisions made
- Keep WordPress plugin MIT (was: GPL by WordPress convention)
- Adopt `langchain` only if WP-XXX Y happens
```

If a decision is made in standup, update the relevant source-of-truth doc immediately.

---

## Testing discipline

### What to test

- Every new function gets a test.
- Every bug fix gets a regression test.
- Every new chain gets a `tests/test_address_vectors.py` entry.
- Every new MCP tool gets an integration test that hits it through the MCP protocol (not direct call).

### Test layout

```
backend/tests/
├── test_chain_vault.py     # CRUD + persistence
├── test_chains.py          # Chain metadata validation
├── test_vault.py           # Encryption + storage
├── conftest.py             # Fixtures
├── test_address_vectors.py # Per-chain golden vectors (Phase 1)
├── test_auth.py            # API key + roles (after WP-004)
├── test_audit_chain.py     # SHA-256 chain integrity (after WP-024)
├── test_agent_safety.py    # HITL + kill switch
├── test_x402.py            # Marketplace (after WP-002, WP-006)
└── test_proof.py           # Merkle + receipts
```

### Coverage gates

- New code: ≥80% line coverage.
- Modified code: coverage can't decrease.
- Security-critical paths (vault, auth, proof, agent_safety): 100% line coverage.

---

## Deployment workflow

```bash
# 1. Push to the deploy host
git push origin main

# 2. On the deploy host, pull, build, and restart
cd /sites/walletpress
git pull
cd backend
make test
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d

# 3. Verify
curl -s http://localhost:8010/health
```

Tagging:

```bash
git tag -a v1.0.0-audit -m "v1.0.0-audit: P0+P1 fixes"
git push origin v1.0.0-audit
```

---

## Agent-specific rules

When you're an AI agent (opencode, aider, Hermes, Claude Code, Continue, Kilo, kimi-code):

1. **Read `WALLETPRESS.md`, `ARCHITECTURE.md`, `SECURITY.md`, `AUDIT.md`, `BUILDER.md`, `ADDRESS_GENERATION.md`** at the start of every session. Use the file tool to confirm they exist before relying on them.
2. **Don't fix bugs you find incidentally.** Log them in AUDIT.md "Known issues" and move on.
3. **Don't propose architectures.** Use ARCHITECTURE.md as the answer to "what should this look like?"
4. **Don't trust PROGRESS.md or ROADMAP.md.** They claim features that don't exist. Run the code.
5. **Don't write to `data/` directory in tests.** Use a tempdir fixture.
6. **Don't commit `.env` files.** Always `gopass` for secrets.
7. **Don't add new dependencies** without updating `requirements.txt` AND `requirements.lock` AND `pyproject.toml`.
8. **Run `make check` before committing.** If it fails, fix the lint/type/test, don't bypass.
9. **Conventional commits only.** Don't merge-squash messages.
10. **Don't create PRs without a WP-NNN ID** in the body.

---

## What gets built where

Decision tree when you need to add a feature:

```
Is this a bug fix?
├── yes → AUDIT.md → find the ID (or add one) → fix in `fix/WP-NNN` branch
└── no, it's a feature
    ├── Does it touch the wallet engine?
    │   ├── yes → chains.py + generator.py + ADDRESS_GENERATION.md + test_address_vectors.py
    │   └── no
    │       ├── Does it expose a new endpoint?
    │       │   ├── yes → routers/* + main.py + OpenAPI regen + WP plugin update
    │       │   └── no
    │       │       ├── Does it expose a new MCP tool?
    │       │       │   ├── yes → agent/mcp_server.py + agent_safety check + HITL flow
    │       │       │   └── no
    │       │       │       ├── Does it change security boundaries?
    │       │       │       │   ├── yes → SECURITY.md update + ARCHITECTURE.md update + threat model
    │       │       │       │   └── no
    │       │       │       │       └── It's core only. Add to the relevant core/ module.
```

This is the **canonical routing rule**. If you're not sure, ask in the standup.

---

## Anti-patterns

We've seen these fail. Don't repeat them:

1. **"I'll just quickly add this feature while I'm in here."** No. PR scope is sacred.
2. **"The test is too hard to write, I'll skip it."** No. Refactor the code so the test is easy.
3. **"I'll just use a global dict for now and persist later."** No. Use the repository pattern from day one.
4. **"The chain is similar enough to BTC, I'll reuse the logic."** No. Each chain has its own format. Test vectors per chain.
5. **"I'll just put a `try/except` around it."** No. Catch the specific exception. Log it. Re-raise with context.
6. **"I'll log the full params dict to debug."** No. Redact secrets before logging.
7. **"I'll hardcode the RPC for now."** No. Use `WP_RPC_{CHAIN}` env var from day one.
8. **"Tests are slow because of LLM calls, I'll mock everything."** No. Mock only at the network boundary. Keep the logic under test.
9. **"I'll commit straight to main."** No. Branch, PR, review, merge.
10. **"I'll update the docs later."** No. Docs in the same PR. Always.

---

## Cadence summary

| Cadence | Activity | Tool |
|---------|----------|------|
| **Every session** | Read source-of-truth docs | editor |
| **Every PR** | `make check` + `make security` | local |
| **Daily** | Standup + push to Talos | git + ssh |
| **Weekly** | Run `make vuln-scan`, update dependencies | tools |
| **Per release** | Cut tag, run pre-release checklist | SECURITY.md |
| **Per chain addition** | Update ADDRESS_GENERATION.md + tests | editor |
| **Per security finding** | Update AUDIT.md + (if design change) ARCHITECTURE.md | editor |

---

## Onboarding a new agent

If you're a new agent arriving cold:

1. Read `WALLETPRESS.md` (5 min)
2. Read `ARCHITECTURE.md` (15 min)
3. Read `SECURITY.md` (10 min)
4. Read `AUDIT.md` (15 min)
5. Skim `ADDRESS_GENERATION.md` (5 min)
6. Read this file (5 min)
7. Run `make check` (5 min)
8. Pick a small WP-NNN item (start with WP-001 or WP-040)
9. Open a PR

Total onboarding: ~1 hour to first useful PR.

---

## See also

- `WALLETPRESS.md` — product summary
- `ARCHITECTURE.md` — system design + roadmap
- `SECURITY.md` — threat model
- `AUDIT.md` — bugs and fixes
- `ADDRESS_GENERATION.md` — chain truth table