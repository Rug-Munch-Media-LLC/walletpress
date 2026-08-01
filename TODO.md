# walletpress — Production TODO
**Last audit:** 2026-07-31 · **Status:** NOT SAFE FOR FUNDS · **Grade:** D (security)

⚠️ **DO NOT FUND WALLETS in the current mounted configuration.** 8 critical security vulnerabilities found.

## 🔴 BLOCKING — SECURITY (Fix before ANY funds touch this system)

- [ ] **CRITICAL: Gate /mcp behind API-key auth** — `main.py:266`: `/mcp/` explicitly exempted from auth. MCP server can decrypt keys, sweep wallets. Attacker self-approves via `agent_confirm` with no authentication. `agent/mcp_server.py:746,122`
- [ ] **CRITICAL: Fix spending-limit bypass** — `agent/mcp_server.py:771`: `check_spending_limit(chain, 0)` — entire wallet sweep validated as 0-amount operation. Record happens after broadcast with `except: pass`.
- [ ] **CRITICAL: Enforce auth on all GET endpoints** — `main.py:261-265`: `require_auth_on_mutations` only blocks writes. Every GET on vault/retention is public: all wallet addresses, labels, balances, tags exposed.
- [ ] **CRITICAL: Fix scope injection** — `chain_vault.py:478-486`: operator can mint API key with `scopes: ["admin"]` → full key export. Validate scopes server-side.
- [ ] **CRITICAL: Fix x402 free key dispenser** — `x402_service.py:110-111`: `MIN_ORDER_USD = 1.00`, `PRICE_PER_WALLET = 0.01` → 99 free wallets with plaintext keys. Credits path accepts any non-empty string. Fix: enforce 1-wallet minimum, verify credits, remove CORS wildcard.
- [ ] **CRITICAL: Fix timelock execution** — `core/smart_wallet.py:682-743`: sends encrypted key blob as raw tx, fakes tx hashes. Implement real decrypt→build→sign→broadcast.
- [ ] **CRITICAL: Fix social recovery** — `smart_wallet.py:295-306`: claimant signature always True for any non-empty sig. Guardian signatures not bound to message (replay). EVM uses SHA-256 not EIP-191 (always fails). Dead-man's switch checks client-supplied address string (no proof).
- [ ] **CRITICAL: Fix wp-plugin login bypass** — unconfigured plugin skips signature verification entirely; configured path calls stub endpoint that always returns `verified: False`, which PHP treats as success. `\n` template never matches real client newlines.

## 🟠 HIGH

- [ ] Fix plaintext key storage on import — `chain_vault.py:240`: when WP_VAULT_PASSWORD unset, keys stored in plaintext. Fail closed.
- [ ] Fix airdrop key loss — `routers/airdrop.py`: generates wallets with no vault password → keys permanently discarded. Any funds sent are lost. Also expose manifest PII without auth.
- [ ] Fix `/derive-address` mnemonic oracle — `chain_vault.py:501-523`: echoes user mnemonic, derives for any operator.
- [ ] Fix `/vault/{id}/full` encrypted blob mislabel — `chain_vault.py:401`: response `private_key_hex` contains base64 AES ciphertext, not decrypted key. Docstring claims decryption.
- [ ] Fix webhook secret exposure + SSRF — returns secrets to any authed user; DNS rebinding bypass.
- [ ] Fix JWT algorithm confusion — `jwt_auth.py:111`: HS256 with public RSA key as HMAC secret → token forgery.
- [ ] Fix license admin key in query param — travels in URL → access logs, browser history.
- [ ] Fix free plan self-upgrade — `routers/hosting.py`: any free user can POST `plan="enterprise"` → $199 tier instantly.
- [ ] Fix admin key not validated — only checks non-empty. `.env.example` ships `change-me-to-a-random-string` as default.

## 🟡 MEDIUM

- [ ] Fix audit log NOT hash-chained — SECURITY.md claims SHA-256 chain; actual is plain append-only JSONL. Either implement or update docs.
- [ ] Fix WP_VAULT_PASSWORD placeholder in .env.example (deploy-as-is = public knowledge)
- [ ] Fix vault DB + api_keys.json created with 0644 (should be 0600)
- [ ] Fix /data directory chmod 0755 (should be 0700)
- [ ] Fix `requirements.lock` incomplete — only 18/50 packages, missing bech32/stellar/xrpl/algorand/etc.
- [ ] Fix vulnerable `ecdsa==0.19.2` — Minerva timing attack, no fix available. Replace library.
- [ ] Fix rate-limit buckets never evicted — unbounded memory per IP.
- [ ] Fix `ALTER TABLE ADD COLUMN` on every `put()` — migrate schema once.
- [ ] Fix DCA scheduler sweeps entire balance — ignores `task.amount`, drains wallet.
- [ ] Fix `admin_key` compared with `==` — timing side-channel (low impact).
- [ ] Fix Solana broadcast uses `skipPreflight: true` — silent tx failures.
- [ ] Fix `wallet_admin.revoke_api_key` uses label as key ID — revocation broken.

## 🟢 LOW

- [ ] Fix `GeneratedWallet.clear_sensitive()` no-op — zeroes fields that are always None. Secrets never cleared from memory.
- [ ] Fix mnemonic held in plaintext on wallet object — echoes to x402 response.
- [ ] Fix `vault.put` returns bool but errors swallowed (silent write failures).
- [ ] Fix partial-generation on failure — persists wallets mid-loop then 500s, no rollback.
- [ ] Fix `egg-info/` committed to repo.
- [ ] Fill STATUS.md from fleet-template (currently unfilled "TBD" template).
- [ ] Fix `mypy` never run in CI despite being installed.
- [ ] Add semgrep, pip-audit, Trivy, SBOM, scorecard to CI.
- [ ] Fix CI test path: `pytest tests/` but tests live in `backend/tests/`.
- [ ] Pin deps with hashes in requirements.lock.

## Tests

- [ ] 490 pass / 5 skip — good quantity, wrong focus. No tests for actual kill chains (unauth MCP, scope injection, x402 free keys, etc.)
- [ ] Add security-specific tests for all 8 critical vulns above
- [ ] Fix CI test path (blocking — current path collects nothing)
