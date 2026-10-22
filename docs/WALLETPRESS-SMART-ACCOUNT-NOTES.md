# WalletPress — Smart Accounts, Session Keys, Passkeys, Paymasters

Scope: what WalletPress (WaaS: wallet engine, vault, x402 marketplace, agent) should
adopt from the OSS smart-account / embedded-wallet stack, and the exact files that change.
Sources are in the ContextCrypto corpus (`codebase_reference_v2_8b`, 8B/4096); every
claim below is cited to library + file + symbol retrieved from it (see **Proofs**).

## 1. Where WalletPress stands today

| Area | Reality in this repo | Gap vs WaaS peers |
|---|---|---|
| Wallet type | EOA only — `wallet_engine/generator.py` (BIP39/BIP32, 55 chains) | no smart account, no counterfactual address |
| Custody | `core/vault.py` AES-256-GCM + Argon2id, one blob + KEK file | no per-tenant DEK, no key rotation, no policy engine |
| Agent guardrails | `core/agent_safety.py`: HITL queue, spending limits, allowlist, tiers, kill switch, hash-chained audit — **all off-chain** | limits die with the server; nothing binds the chain |
| Recovery | `core/smart_wallet.py`: guardian signatures, dead-man switch, time locks — **off-chain, by design** | not portable, no on-chain enforcement |
| Auth | API key + scopes (`core/auth.py`), TOTP (`core/totp.py`) | no passkey/WebAuthn |
| Payments | `x402_service.py` + `coffer_client.py` verify/settle, fail-closed | single quote, no `accepts[]`, weak replay/idempotency on `X-PAYMENT` |
| Gas | caller-funded | no paymaster/sponsorship |

**Drift to fix first:** `ARCHITECTURE.md` line ~100 calls `core/smart_wallet.py`
"ERC-4337 smart wallet logic (754 lines)". The module is 889 lines of *off-chain*
social recovery ("NO SMART CONTRACTS NEEDED"). Correct the doc; there is no 4337 code
anywhere in `backend/` today.

## 2. Per-module plan

### 2.1 `wallet_engine/` — add a smart-account type
- New `wallet_engine/smart_accounts.py`: counterfactual address from
  `CREATE2(factory, salt=keccak(owner,index), initCodeHash)` against EntryPoint v0.7/v0.8,
  plus `buildInitCode()` and `toUserOperation()` skeleton.
- `routers/chain_vault.py`: add `POST /chains/smart-account/predict` (no key material
  returned) beside `POST /generate` / `/derive-address`; persist `account_type`
  (`eoa` | `smart`) and `factory`/`salt` in the vault record.
- Do **not** conflate with `core/smart_wallet.py`; that module keeps its social-recovery role.

### 2.2 `core/agent_safety.py` — session keys the chain can enforce
- New `core/session_keys.py`: request permissions with ERC-7715
  (`wallet_grantPermissions`, `expiry`, `permissions[]`, `signer`), translate the granted
  permission into the account's validator, and store `permission_id` + `context` next to
  the existing spend counters.
- `check_spending_limit()` keeps local policy **above** the chain (defence in depth) but
  the on-chain validator becomes the backstop when the backend is compromised.
- Expiry must be short for agent keys; redelegation is a separate, explicit grant.

### 2.3 Passkey onboarding (`core/passkeys.py`, `wp-plugin/`)
- New `core/passkeys.py`: WebAuthn registration/authentication verification
  (`startRegistration`/`verifyRegistration`, challenge store, rpId/origin checks) —
  the pattern `MasterKale/SimpleWebAuthn` implements; reuse it rather than hand-rolling.
- Endpoints `/api/v1/auth/passkey/{register,begin,complete}`; store credential id +
  COSE public key per user; the smart-account owner is the passkey signer
  (Coinbase Smart Wallet model: `ERC1271` + `MultiOwnable`).
- `wp-plugin/includes/class-walletpress-auth.php`: passkey button next to the API-key flow;
  no seed phrase in the browser.

### 2.4 Paymaster / gasless first action (`core/paymaster.py`)
- New module: `sponsorUserOperation()` → `pm_getPaymasterStubData` / `pm_getPaymasterData`
  (or Alchemy Gas Manager policy id), inject `paymasterAndData` into the UserOperation.
- Config: `WP_PAYMASTER_URL`, `WP_PAYMASTER_POLICY_ID`, `WP_SPONSOR_MAX_USD`.
- Gate: only sponsor `wallet.created` first-tx and marketplace-delivered wallets; a
  per-tenant cap is mandatory or sponsorship is a free-money endpoint.

### 2.5 EIP-7702 delegation for existing EOAs (`wallet_engine/delegation.py`)
- Build the authorization tuple `(chain_id, delegation_target, nonce)` + type-4 tx so an
  already-printed EOA can delegate to a delegator with caveats, instead of migrating keys.
- `routers/tx_broadcaster.py`: accept `delegation` in the send payload; refuse when the
  chain config lacks 7702 support.
- Caveats/enforcers carry the limits (spend cap, allowlist, expiry) — the same policy
  vocabulary as `agent_safety`, now enforceable on-chain.

### 2.6 Vault → per-tenant custody (`core/vault.py`, new `core/policy_engine.py`)
- Per-tenant DEK wrapped by the existing KEK; `rotate_dek(tenant)` + `rotate_kek()`
  endpoints in `routers/wallet_admin.py`; keep ciphertext-only storage.
- New `core/policy_engine.py`: rules `{tenant, chain, target, selector, max_amount,
  period, expires_at, require_approval}` evaluated before every sign; the HITL queue is
  the `require_approval` executor, not a parallel system.
- `X-Idempotency-Key` on sign/broadcast; replay must return the first result.

### 2.7 x402 paid printing (`x402_service.py`, `coffer_client.py`)
- Return a proper 402 challenge with `accepts[]` (asset, network, maxAmountRequired,
  payTo, resource, scheme `exact`) instead of a single price; keep local policy first.
- Verify → settle ordering stays; add `payment_payload_hash` unique index so a replayed
  `X-PAYMENT` cannot print twice (settle must be idempotent).
- Only then hand back keys; coffer unreachable ⇒ 402, never fulfilment.

### 2.8 Audit / webhooks / rate limits parity
- `core/webhooks.py`: signing-key rotation (`kid` in header, two active keys), replay
  window check on consumers, delivery log retention.
- `core/rate_limit.py`: buckets keyed by tenant API key (not just IP) for
  `sign`/`broadcast`/`generate`; expose remaining quota in headers.
- `core/audit.py` + `agent_safety.audit_log`: emit `wallet.created|signed|delegated|
  permission.granted` to webhooks from the same hash-chained record.

## 3. Security invariants (do not trade away)
1. Local policy is evaluated **before** any facilitator/paymaster call (already true for x402).
2. Session-key and 7702 caveats never grant more than the tenant's server-side policy.
3. Passkey verification server-side only; no credential material in the WP plugin.
4. Keys never leave the vault unencrypted; sponsorship never signs for an unauthenticated tenant.
5. Every new write path emits an audit record and honours the kill switch.

## 4. Proofs (corpus citations)
1. **UserOperation flow** — `eth-infinitism/account-abstraction`,
   `contracts/core/EntryPoint.sol::handleOps` → `_callValidateUserOp` (validation phase)
   → `_executeUserOp`/`innerHandleOp` (execution phase).
2. **Session key / delegated permission** — `wevm/viem`,
   `src/experimental/erc7715/actions/grantPermissions.ts::grantPermissions`
   (`{account, expiry, permissions, signer}`) + `src/types/eip1193.ts::WalletGrantPermissionsParameters`.
3. **ERC-7715 grant shape** — same `grantPermissions` + `erc7715Actions` decorator
   ("request permissions from a wallet to perform actions on behalf of a user").
4. **EIP-7702 delegation** — `ithacaxyz/account`, `src/Orchestrator.sol::
   accountImplementationOf` and `src/IthacaAccount.sol::upgradeProxyAccount` via
   `LibEIP7702.delegationAndImplementationOf` / `upgradeProxyDelegation`.
5. **Passkey wallet creation** — `coinbase/smart-wallet`, `src/CoinbaseSmartWallet.sol`
   (ERC1271 + IAccount + MultiOwnable) and `CoinbaseSmartWalletFactory`;
   client flow `pimlicolabs/permissionless.js` `createPasskeyServerClient` +
   `startRegistration`/`verifyRegistration`.
6. **Paymaster sponsorship** — `bcnmy/nexus`, `contracts/Nexus.sol::validateUserOp`
   (payPrefund/onlyEntryPoint) + `contracts/mocks/MockPaymaster.sol` (VerifyingPaymaster);
   EntryPoint side is `_validatePaymasterUserOp` in the 4337 repo.

## 5. Remaining gaps
- No OSS **Circle programmable wallets SDK** (API-only, closed) — only
  `circlefin/circle-nodejs-sdk` (Apache-2.0) is indexed for API shape.
- **Turnkey / Privy / Dynamic / Web3Auth**: Turnkey + Crossmint ingested (SDK, Apache-2.0);
  Privy and Dynamic SDKs are not public; **Web3Auth is proprietary** ("all rights reserved",
  Torus Labs) and was deliberately excluded.
- **ZeroDev Kernel** has no licence file in-repo → excluded despite being the reference
  session-key implementation; revisit if a licence lands.
- Lit Protocol `LIT-Protocol/js-sdk` is 404 (moved/private) → no PKP coverage.
- ERC-7710 redelegation depth limits and 7715 permission-response validation need a
  dedicated review before shipping agent keys.
