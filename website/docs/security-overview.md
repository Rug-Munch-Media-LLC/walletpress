---

title: "Security Model — Defense in Depth"
description: "AES-256-GCM vault, Argon2id key derivation, SHA-256 audit log, HITL on every write, kill switch, Arweave proofs. Not a hot wallet. Not a custodial service."
keywords: [security, vault, encryption, aes-256, argon2id, hitl, arweave, audit, wallet security]
unlisted: false
---

// WpBadge import removed for MDX compatibility

*Production Hardened*

**Defense in depth. Not a hot wallet. Not a custodial service. Your infrastructure, your keys, your vault.**

---

## Vault Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                        │
│  REST API  │  MCP Server  │  CLI  │  WordPress Plugin      │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      VAULT SERVICE                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ AES-256-GCM │  │ Argon2id    │  │ SHA-256 Audit Log   │  │
│  │ Encryption  │  │ Key Deriv.  │  │ (chained, immutable)  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                          │
│  PostgreSQL (encrypted columns)  │  Redis (encrypted)       │
└─────────────────────────────────────────────────────────────┘
```

---

## Encryption at Rest

### AES-256-GCM

- **Algorithm:** AES-256 in Galois/Counter Mode
- **Key Size:** 256 bits
- **Nonce:** 96-bit random per encryption
- **Tag:** 128-bit authentication tag
- **Library:** Rust `aes-gcm` (constant-time, audited)

**What's Encrypted:**
- Mnemonics (BIP39 seed phrases)
- Private keys (derived and stored)
- API keys (internal service keys)
- Webhook secrets
- x402 payment proofs

**What's NOT Encrypted (by design):**
- Public addresses (derived from public keys)
- Derivation paths
- Labels and metadata
- Chain identifiers

### Argon2id Key Derivation

```rust
// Vault key derivation
let vault_key = argon2id::derive_key(
    password: &VAULT_KEY,           // From env (32-byte base64)
    salt: &VAULT_SALT,              // Per-deployment, 32 bytes
    memory_cost: 65536,             // 64 MB
    time_cost: 3,                   // 3 iterations
    parallelism: 4,                 // 4 threads
    output_length: 32               // 256-bit key
);
```

**Parameters chosen for:** ~100ms derivation on modern CPU, ~64MB memory (ASIC-resistant)

### Key Hierarchy

```
VAULT_KEY (env) + VAULT_SALT (config)
    │
    ├── argon2id (64MB, 3 iter, 4 threads)
    │       │
    │       └── MASTER_KEY (256-bit)
    │              │
    │              ├── AES-256-GCM key (mnemonics)
    │              ├── AES-256-GCM key (private keys)
    │              ├── AES-256-GCM key (API keys)
    │              └── AES-256-GCM key (webhooks)
    │
    └── HMAC-SHA256 key (audit log chaining)
```

---

## Audit Logging (SHA-256 Chained)

Every vault operation creates an immutable audit entry:

```json
{
  "id": "aud_abc123",
  "timestamp": "2026-11-02T12:00:00.123Z",
  "operation": "generate_wallet",
  "actor": "api_key:wp_live_EXAMPLE",
  "resource": "wlt_xyz789",
  "details": {
    "chains": ["ethereum", "solana"],
    "derivation_path": "m/44'/60'/0'/0/0"
  },
  "prev_hash": "sha256:a1b2c3d4...",
  "hash": "sha256:e5f6g7h8..."
}
```

**Properties:**
- **Immutable:** Each entry includes `prev_hash` — tampering breaks chain
- **Verifiable:** Full chain verifiable from genesis
- **Exportable:** `GET /api/v1/audit/export` for compliance
- **Retention:** Configurable (default 7 years)

**Verification:**
```bash
# Verify audit chain integrity
curl https://api.walletpress.cc/api/v1/audit/verify
# Returns: {"valid": true, "entries": 142847, "genesis": "sha256:..."}
```

---

## Human-In-The-Loop (HITL)

**Every mutating operation requires explicit approval:**

| Operation                   | HITL Required | Approver                          |
| --------------------------- | ------------- | --------------------------------- |
| Generate wallet             | ✅            | API key owner / MCP human         |
| Derive address              | ✅            | API key owner / MCP human         |
| Sign transaction            | ✅            | API key owner / MCP human         |
| Sign message                | ✅            | API key owner / MCP human         |
| Update wallet metadata      | ✅            | API key owner                     |
| Delete wallet (soft)        | ✅            | API key owner                     |
| Purge wallet (irreversible) | ✅            | API key owner + `X-Confirm-Purge` |
| x402 wallet generation      | ✅            | Payment proof + human             |

**MCP HITL Flow:**
```
Agent proposes → Human reviews → Approve/Reject/Modify → Execute on approval
```

**REST API:** Approval via `POST /api/v1/approvals/{id}/approve` with same API key.

---

## Kill Switch

```bash
# Emergency vault seal (irreversible without VAULT_KEY)
POST /api/v1/admin/vault/seal
Authorization: Bearer wp_admin_...

# Response
{
  "status": "sealed",
  "sealed_at": "2026-11-02T12:00:00Z",
  "note": "All encryption keys zeroed. Requires VAULT_KEY to unseal."
}
```

**Effects:**
- All encryption keys zeroed in memory
- New operations rejected with `vault-locked` (503)
- Audit log continues (append-only)
- Requires `VAULT_KEY` + restart to unseal

---

## Arweave Proof of Generation

Every wallet generation creates an immutable proof:

```json
{
  "wallet_id": "wlt_abc123",
  "chains": {
    "ethereum": "0x742d35...",
    "solana": "7xKXtg..."
  },
  "mnemonic_hash": "sha256:abc123...",
  "derivation_paths": {
    "ethereum": "m/44'/60'/0'/0/0",
    "solana": "m/44'/501'/0'/0'"
  },
  "timestamp": "2026-11-02T12:00:00Z",
  "arweave_tx": "abc123def456",
  "arweave_url": "https://arweave.net/abc123def456"
}
```

**Properties:**
- **Immutable:** Arweave is permanent, tamper-proof
- **Verifiable:** Anyone can fetch and verify
- **Includes:** Mnemonic hash (not mnemonic), addresses, paths, timestamp
- **Cost:** ~$0.01 per wallet (paid by WalletPress, not user)

---

## Access Control

### API Keys

| Scope       | Permissions                       | Rate Limit |
| ----------- | --------------------------------- | ---------- |
| `wp_live_*` | Full access (all chains, all ops) | 100 req/s  |
| `wp_test_*` | Testnet only, no x402             | 10 req/s   |
| `wp_read_*` | Read-only (list, get, verify)     | 100 req/s  |
| `wp_mcp_*`  | MCP server access                 | 60 req/min |

### IP Allowlisting

```bash
# Configure in dashboard or API
POST /api/v1/api-keys/wp_live_abc/allowlist
{"ips": ["192.168.1.0/24", "198.51.100.5"]}
```

### Rate Limiting

| Tier       | Requests/Second | Burst | Daily Cap |
| ---------- | --------------- | ----- | --------- |
| Free       | 10              | 20    | 10,000    |
| Pro        | 100             | 200   | 1,000,000 |
| Enterprise | 1000            | 2000  | Unlimited |

---

## Compliance & Audits

### SOC 2 Type II (In Progress)

- Encryption at rest: ✅
- Encryption in transit: ✅ (TLS 1.3)
- Access control: ✅
- Audit logging: ✅
- Incident response: ✅
- Vendor management: ✅

### Penetration Testing

- Annual third-party pentest (last: 2026-06)
- Continuous bug bounty (Immunefi)
- Dependency scanning: daily (GitHub Dependabot + Trivy)

### Certifications Targeted

- SOC 2 Type II (Q1 2027)
- ISO 27001 (2027)
- CCSS Level 3 (for custodial features)

---

## Responsible Disclosure

Found a vulnerability? Email **security@walletpress.cc** or submit via [Immunefi](https://immunefi.com/bounty/walletpress).

**Scope:** WalletPress core, API, MCP, CLI, WordPress plugin, smart contracts (if any).

**Rewards:** Up to $50,000 for critical vulnerabilities.

**Safe Harbor:** We authorize good-faith research. No legal action for compliant reports.

---

## Next

- [Vault Deep Dive →](security/vault.md)
- [Audit Log API →](security/audit-log.md)
- [HITL Flow →](../mcp/hitl-flow.md)
- [Arweave Proofs →](security/arweave-proofs.md)
- [Incident Response →](security/incident-response.md)
