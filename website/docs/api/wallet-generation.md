---

title: "API Reference — Wallet Generation"
description: "Complete REST API reference for wallet generation, management, and operations. OpenAPI 3.1 spec with worked examples."
keywords: [api, wallet generation, rest api, openapi, bip39, derivation]
unlisted: false
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';


## Base URL

```
Production:  https://api.walletpress.yourdomain.com/api/v1
Local:       http://localhost:8010/api/v1
```

All endpoints require `Authorization: Bearer <token>` header unless marked **public**.

---

## Authentication

```bash
# Get token (if using API key auth)
curl -X POST https://api.walletpress.cc/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "wp_live_EXAMPLE"}'

# Response
{
  "access_token": "<jwt>",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

---

## Wallet Generation

### Generate New Wallet

- **POST** `/wallets` — Generate new multi-chain wallet

**Request:**

```json
{
  "chains": ["ethereum", "solana", "bitcoin", "polygon", "arbitrum", "optimism", "base", "bnb"],
  "label": "user-wallet-001",
  "derivation_path": "m/44'/60'/0'/0/0",
  "passphrase": "optional-bip39-passphrase",
  "entropy": "optional-hex-entropy-for-deterministic-generation",
  "metadata": {
    "user_id": "usr_abc123",
    "purpose": "trading-bot"
  }
}
```

**Response (201):**

```json
{
  "id": "wlt_abc123def456",
  "label": "user-wallet-001",
  "mnemonic": "<your-bip39-mnemonic>",
  "chains": {
    "ethereum": {
      "address": "0x742d35Cc6634C0532925a3b8D4C0532925a3b8D4",
      "derivation_path": "m/44'/60'/0'/0/0",
      "public_key": "<public-key-hex>",
      "chain_code": "0x1234..."
    },
    "solana": {
      "address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
      "derivation_path": "m/44'/501'/0'/0'",
      "public_key": "<solana-public-key>"
    },
    "bitcoin": {
      "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
      "derivation_path": "m/84'/0'/0'/0/0",
      "public_key": "0x02abcdef...",
      "address_type": "p2wpkh"
    }
  },
  "created_at": "2026-11-02T12:00:00Z",
  "arweave_proof": "https://arweave.net/abc123def456",
  "proof_tx_id": "abc123def456"
}
```

**Fields:**

| Field             | Type       | Description                                                             |
| ----------------- | ---------- | ----------------------------------------------------------------------- |
| `chains`          | `string[]` | **Required.** Chain IDs from [supported chains](../chains-supported.md) |
| `label`           | `string`   | Human-readable label (max 100 chars)                                    |
| `derivation_path` | `string`   | BIP32 path (default: `m/44'/60'/0'/0/0` for EVM)                        |
| `passphrase`      | `string`   | Optional BIP39 passphrase (adds 25th word)                              |
| `entropy`         | `string`   | Optional 32-byte hex for deterministic generation                       |
| `metadata`        | `object`   | Arbitrary key-value for your tracking                                   |

---

### Derive Address at Path

- **POST** `/wallets/{id}/derive` — Derive new address at custom path

**Request:**

```json
{
  "chain": "ethereum",
  "derivation_path": "m/44'/60'/0'/0/5",
  "label": "deposit-address-5"
}
```

**Response (200):**

```json
{
  "chain": "ethereum",
  "address": "0x88aBcD...",
  "derivation_path": "m/44'/60'/0'/0/5",
  "index": 5,
  "public_key": "0x04...",
  "created_at": "2026-11-02T12:05:00Z"
}
```

---

### Derive Multiple Addresses (Batch)

- **POST** `/wallets/{id}/derive/batch` — Derive multiple addresses in one call

**Request:**

```json
{
  "chain": "ethereum",
  "start_index": 0,
  "count": 20,
  "label_prefix": "deposit-"
}
```

**Response (200):**

```json
{
  "chain": "ethereum",
  "addresses": [
    { "index": 0, "address": "0x...", "derivation_path": "m/44'/60'/0'/0/0" },
    { "index": 1, "address": "0x...", "derivation_path": "m/44'/60'/0'/0/1" },
    "..."
  ],
  "created_at": "2026-11-02T12:10:00Z"
}
```

---

## Wallet Management

### List Wallets

- **GET** `/wallets` — List all wallets with pagination

**Query Parameters:**

| Param    | Type    | Default      | Description                                       |
| -------- | ------- | ------------ | ------------------------------------------------- |
| `limit`  | integer | 50           | Max results (1-200)                               |
| `offset` | integer | 0            | Pagination offset                                 |
| `label`  | string  | -            | Filter by label (partial match)                   |
| `chain`  | string  | -            | Filter by chain presence                          |
| `sort`   | string  | `created_at` | Sort field: `created_at`, `label`, `chains_count` |
| `order`  | string  | `desc`       | `asc` or `desc`                                   |

**Response (200):**

```json
{
  "wallets": [
    {
      "id": "wlt_abc123",
      "label": "user-wallet-001",
      "chains_count": 8,
      "primary_chain": "ethereum",
      "created_at": "2026-11-01T10:00:00Z",
      "updated_at": "2026-11-02T12:00:00Z"
    }
  ],
  "pagination": {
    "total": 142,
    "limit": 50,
    "offset": 0,
    "has_more": true
  }
}
```

---

### Get Wallet Details

- **GET** `/wallets/{id}` — Get full wallet details including all derived addresses

**Response (200):**

```json
{
  "id": "wlt_abc123",
  "label": "user-wallet-001",
  "mnemonic": "<your-bip39-mnemonic>",
  "chains": {
    "ethereum": {
      "addresses": [
        {
          "derivation_path": "m/44'/60'/0'/0/0",
          "address": "0x742d35...",
          "label": "primary",
          "created_at": "2026-11-01T10:00:00Z"
        },
        {
          "derivation_path": "m/44'/60'/0'/0/1",
          "address": "0x88aBcD...",
          "label": "deposit-1",
          "created_at": "2026-11-01T11:00:00Z"
        }
      ]
    },
    "solana": {
      "addresses": [
        {
          "derivation_path": "m/44'/501'/0'/0'",
          "address": "7xKXtg...",
          "label": "primary",
          "created_at": "2026-11-01T10:00:00Z"
        }
      ]
    }
  },
  "metadata": { "user_id": "usr_abc123" },
  "arweave_proofs": [
    { "tx_id": "abc123", "url": "https://arweave.net/abc123", "created_at": "2026-11-01T10:00:00Z" }
  ],
  "created_at": "2026-11-01T10:00:00Z",
  "updated_at": "2026-11-02T12:00:00Z"
}
```

---

### Update Wallet

- **PATCH** `/wallets/{id}` — Update wallet metadata

**Request:**

```json
{
  "label": "new-label",
  "metadata": {
    "user_id": "usr_abc123",
    "status": "active",
    "tags": ["trading", "bot"]
  }
}
```

---

### Delete Wallet

- **DELETE** `/wallets/{id}` — Delete wallet (soft delete — vault data preserved)

**Response (200):**

```json
{
  "id": "wlt_abc123",
  "status": "deleted",
  "deleted_at": "2026-11-02T12:00:00Z",
  "note": "Vault data preserved. Use /wallets/{id}/purge to permanently erase."
}
```

---

### Purge Wallet (Irreversible)

- **DELETE** `/wallets/{id}/purge` — Permanently erase wallet from vault

**Requires:** `X-Confirm-Purge: true` header

**Response (200):**

```json
{
  "id": "wlt_abc123",
  "status": "purged",
  "purged_at": "2026-11-02T12:00:00Z"
}
```

---

## Address Operations

### Get All Addresses for Wallet

- **GET** `/wallets/{id}/addresses` — List all derived addresses across all chains

**Query Parameters:**

| Param             | Type   | Description           |
| ----------------- | ------ | --------------------- |
| `chain`           | string | Filter by chain       |
| `derivation_path` | string | Filter by path prefix |
| `label`           | string | Filter by label       |

---

### Sign Transaction

- **POST** `/wallets/{id}/sign` — Sign transaction with wallet key

**Request:**

```json
{
  "chain": "ethereum",
  "derivation_path": "m/44'/60'/0'/0/0",
  "transaction": {
    "to": "0x742d35Cc6634C0532925a3b8D4C0532925a3b8D4",
    "value": "1000000000000000000",
    "gas": "21000",
    "gasPrice": "20000000000",
    "nonce": 0,
    "chainId": 1
  },
  "encoding": "rlp"  // or "eip155", "eip2718"
}
```

**Response (200):**

```json
{
  "signed_transaction": "0xf86a808504a817c80082520894742d35cc6634c0532925a3b8d4c0532925a3b8d4880de0b6b3a76400008025a0...",
  "signature": {
    "r": "0x...",
    "s": "0x...",
    "v": 27
  },
  "hash": "0xabc123..."
}
```

---

### Sign Message

- **POST** `/wallets/{id}/sign-message` — Sign arbitrary message (EIP-191, EIP-712)

**Request:**

```json
{
  "chain": "ethereum",
  "derivation_path": "m/44'/60'/0'/0/0",
  "message": "Hello, WalletPress!",
  "encoding": "eip191"  // or "eip712", "raw"
}
```

---

## x402 Wallet Generation

### Generate via x402 (Pay-Per-Use)

- **POST** `/x402/wallet` — Generate wallet via x402 payment

**Headers:**

```
X-Payment: x402 <payment-proof>
Content-Type: application/json
```

**Request:**

```json
{
  "chains": ["ethereum", "solana"],
  "label": "x402-wallet-001"
}
```

**Response (201):**

Same as wallet generation, plus:

```json
{
  "...": "...",
  "x402_payment": {
    "tx_hash": "0xabc123...",
    "amount_usd": 0.01,
    "chain": "base",
    "settled_at": "2026-11-02T12:00:00Z"
  }
}
```

---

## Error Responses

All errors follow RFC 7807 Problem Details:

```json
{
  "type": "https://walletpress.cc/errors/validation-error",
  "title": "Validation Error",
  "status": 422,
  "detail": "Invalid derivation path for chain 'solana'",
  "instance": "/api/v1/wallets",
  "errors": [{ "field": "derivation_path", "message": "Solana uses m/44'/501'/0'/0' format" }]
}
```

**Common Error Types:**

| Type                 | Status | Description                        |
| -------------------- | ------ | ---------------------------------- |
| `validation-error`   | 422    | Request body invalid               |
| `not-found`          | 404    | Wallet/address not found           |
| `unauthorized`       | 401    | Invalid/missing token              |
| `rate-limited`       | 429    | Too many requests                  |
| `vault-locked`       | 503    | Vault key mismatch or vault sealed |
| `payment-required`   | 402    | x402 payment needed                |
| `insufficient-funds` | 402    | x402 payment amount too low        |

---

## Rate Limits

| Tier       | Requests/Second | Burst |
| ---------- | --------------- | ----- |
| Free       | 10              | 20    |
| Pro        | 100             | 200   |
| Enterprise | 1000            | 2000  |

Headers returned:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

---

## OpenAPI Spec

Download: [openapi.json](/api/openapi.json) | [openapi.yaml](/api/openapi.yaml)

Interactive: [Swagger UI](/docs) | [Redoc](/redoc)

---

## Next

- [Wallet Management →](wallet-management.md)
- [Address Derivation →](address-derivation.md)
- [Signing →](signing.md)
- [x402 Marketplace →](../x402/overview.md)
