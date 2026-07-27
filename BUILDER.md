# WalletPress — Daily Builder Workflow

> **Status:** Canonical. Owner: WalletPress Engineering.
> **Last updated:** 2026-07-27.
> **Audience:** Every AI agent and engineer working on WalletPress. Read on session start.
> **Purpose:** The single workflow every contributor follows so nothing gets duplicated, every change has context, and the repo stays coherent day over day.

---

## TL;DR — Read this first

Every session, every agent, every engineer:

1. **Read the four canonical docs in order:** WALLETPRESS.md → ARCHITECTURE.md → SECURITY.md → AUDIT.md.
2. **Pick from the open work list** below. Don't pick from scratch — the list is the canonical "what's next."
3. **Touch only what's assigned.** If you find a related bug, log it in AUDIT.md "Known issues" and move on. Don't fix it in this PR.
4. **One logical change per PR.** Conventional commits. Tests in the same PR.
5. **Push daily** (`git push origin main`).
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

| ID | Item | Status |
|----|------|--------|
| WP-001 | Disable 17 BROKEN chains in chains.py | **DONE** (2026-06-30) |
| WP-002 | Fix x402 credits verification (no payment = no credit) | **DONE** (2026-06-30) |
| WP-003 | Migrate hosted passwords to Argon2id | **DONE** (2026-06-30) |
| WP-004 | Persist team keys + role enforcement | **DONE** (2026-06-30) |
| WP-005 | KEK file backend (replace env-only vault password) | **DONE** (2026-06-30) |
| WP-006 | Implement or rename `wallet_sweep` and DCA scheduler | **DONE** (2026-06-30) |

### WP-021 → WP-040 — P1 from AUDIT.md

| ID | Item | Status |
|----|------|--------|
| WP-021 | `verify()` writes on every read (perf + race) | open |
| WP-022 | Add real Alembic migrations (currently dead code) | open |
| WP-023 | Remove ALTER-on-every-put in vault.py | open |
| WP-024 | Audit log integrity chain (SHA-256) | open |
| WP-025 | Redact mnemonic from audit log | open |
| WP-026 | Fix x402 verify_order DB path | open |
| WP-027 | x402 keys-in-body opt-in flag | open |
| WP-028 | x402 xpub derivation correct address format per chain | open |
| WP-029 | LLM call timeout + per-key rate limit | open |
| WP-030 | Orchestrator HITL bypass fix | open |
| WP-031 | Plan JSON schema validation (anti-prompt-injection) | open |
| WP-032 | audit_log hash chain mutex | open |
| WP-033 | DCA scheduler actually executes | open |
| WP-034 | Receipt signing key envelope encryption | open |

### WP-040 → WP-060 — Phase 1 broken chains (per-chain work)

| ID | Chain | Status |
|----|-------|--------|
| WP-040 | Stellar (xlm) | **DONE** (2026-06-30) |
| WP-041 | Tezos (xtz) | **DONE** (2026-06-30) |
| WP-042 | Injective (inj) | **DONE** (2026-06-30) |
| WP-043 | Cosmos Hub (atom) | **DONE** (2026-06-30) |
| WP-044 | Osmosis (osmo) | **DONE** (2026-06-30) |
| WP-045 | Sei (sei) | **DONE** (2026-06-30) |
| WP-046 | Juno (juno) | **DONE** (2026-06-30) |
| WP-047 | Evmos (evmos) | **DONE** (2026-06-30) |
| WP-048 | Algorand (algo) | **DONE** (2026-06-30) |
| WP-049 | TON | **DONE** (2026-06-30) |
| WP-050 | Filecoin (fil) | **DONE** (2026-06-30) |
| WP-051 | Nano (xno) | **DONE** (2026-06-30) |
| WP-052 | Polkadot (dot) — sr25519 | **DONE** (2026-06-30) |
| WP-053 | Kusama (ksm) — sr25519 | **DONE** (2026-06-30) |
| WP-054 | Monero (xmr) | **DONE** (2026-06-30) |
| WP-055 | Cardano (ada) — Bech32 stake | **DONE** (2026-06-30) |
| WP-056 | Bitcoin Cash (bch) — cashaddr | **DONE** (2026-06-30) |
| WP-057 | XRP — custom alphabet | **DONE** (2026-06-30) |
| WP-058 | Zcash (zec) — prefix fix | **DONE** (2026-06-30) |
| WP-059 | BTC segwit variants | open |

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

### What NOT to do in a PR

1. **Don't bundle unrelated changes.** One logical change per PR.
2. **Don't refactor while fixing.** That's two PRs.
3. **Don't update PROGRESS.md / ROADMAP.md** unless you're explicitly rewriting those docs.
4. **Don't add dependencies** without a justification paragraph in the PR body.
5. **Don't change the public API** without updating the WP plugin or SDK in the same PR.
6. **Don't add new chains** without ADDRESS_GENERATION.md update + tests.

---

## Testing discipline

### What to test

- Every new function gets a test.
- Every bug fix gets a regression test.
- Every new chain gets a `tests/test_address_vectors.py` entry.

### Coverage gates

- New code: ≥80% line coverage.
- Modified code: coverage can't decrease.

---

## Anti-patterns

We've seen these fail. Don't repeat them:

1. **"I'll just quickly add this feature while I'm in here."** No. PR scope is sacred.
2. **"The test is too hard to write, I'll skip it."** No. Refactor the code so the test is easy.
3. **"I'll just use a global dict for now and persist later."** No. Use the repository pattern from day one.
4. **"The chain is similar enough to BTC, I'll reuse the logic."** No. Each chain has its own format. Test vectors per chain.
5. **"I'll just put a `try/except` around it."** No. Catch the specific exception. Log it. Re-raise with context.
6. **"I'll log the full params dict to debug."** No. Redact secrets before logging.
7. **"I'll hardcode the RPC for now."** No. Use environment variables from day one.
8. **"Tests are slow because of LLM calls, I'll mock everything."** No. Mock only at the network boundary.
9. **"I'll commit straight to main."** No. Branch, PR, review, merge.
10. **"I'll update the docs later."** No. Docs in the same PR. Always.
