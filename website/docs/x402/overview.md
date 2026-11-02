---

title: "x402 Marketplace — Pay-Per-Use Wallet Generation"
description: "HTTP 402 Payment Required. USDC on Solana, Base, Arbitrum, Ethereum. No API keys, no monthly bills. $0.01 per wallet. Referral revenue sharing built in."
keywords: [x402, http 402, micropayments, usdc, pay per use, wallet generation, ai agent payments]
unlisted: false
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';


**Beta**

**Pay-per-use via HTTP 402. USDC on Solana, Base, Arbitrum, Ethereum. Settlement finality in under 2 seconds on Solana, under 15 seconds on EVM L2s. No API keys, no monthly bills.**

---

## How x402 Works

```
┌─────────────┐     HTTP 402      ┌─────────────┐
│   Client    │ ────────────────► │   Server    │
│  (AI Agent) │  X-Payment: ...   │ (WalletPress)│
└─────────────┘                   └─────────────┘
       ▲                                 │
       │         201 + Wallet            │
       └─────────────────────────────────┘
```

1. Client requests wallet generation
2. Server responds `402 Payment Required` with payment invoice
3. Client pays on-chain (USDC), presents transaction hash
4. Server verifies, generates wallet, returns result

---

## Quickstart

### cURL

```bash
# Request wallet (gets 402)
curl -X POST https://api.walletpress.cc/api/v1/x402/wallet \
  -H "Content-Type: application/json" \
  -d '{"chains": ["ethereum", "solana"], "label": "x402-wallet-001"}'

# Response: 402 Payment Required
{
  "error": "payment_required",
  "payment": {
    "amount_usd": 0.01,
    "amount_usdc": "0.01",
    "chain": "base",
    "recipient": "0x742d35Cc6634C0532925a3b8D4C0532925a3b8D4",
    "invoice_id": "inv_abc123",
    "expires_at": "2026-11-02T12:10:00Z"
  }
}

# Pay on-chain, then retry with payment proof
curl -X POST https://api.walletpress.cc/api/v1/x402/wallet \
  -H "Content-Type: application/json" \
  -H "X-Payment: x402 eyJwcm9vZiI6I..." \
  -d '{"chains": ["ethereum", "solana"], "label": "x402-wallet-001"}'

# Response: 201 Created with wallet
```

### Python (with x402 client)

```python
from x402 import X402Client

client = X402Client(
    base_url="https://api.walletpress.cc",
    wallet="your_wallet_client"  # eth_account, solana keypair, etc.
)

wallet = await client.post("/api/v1/x402/wallet", json={
    "chains": ["ethereum", "solana"],
    "label": "my-x402-wallet"
})
# Handles 402, payment, retry automatically
```

### JavaScript/TypeScript

```typescript
import { x402Fetch } from 'x402-client';

const wallet = await x402Fetch(
  'https://api.walletpress.cc/api/v1/x402/wallet',
  {
    method: 'POST',
    body: JSON.stringify({
      chains: ['ethereum', 'solana'],
      label: 'my-x402-wallet',
    }),
  },
  {
    wallet: window.ethereum, // or any EIP-1193 provider
  },
);
```

---

## Supported Settlement Chains

| Chain        | Token | Settlement Time | Min Amount | Network Fee |
| ------------ | ----- | --------------- | ---------- | ----------- |
| **Solana**   | USDC  | < 2 seconds     | $0.01      | ~$0.00025   |
| **Base**     | USDC  | < 2 seconds     | $0.01      | ~$0.001     |
| **Arbitrum** | USDC  | < 5 seconds     | $0.01      | ~$0.005     |
| **Ethereum** | USDC  | < 15 seconds    | $0.01      | ~$0.02-0.50 |

**Recommendation:** Use **Solana** or **Base** for fastest/cheapest settlement.

---

## Free Tier

Every API key gets **100 free wallet generations per day**. After that, x402 kicks in automatically.

```bash
# Check your tier and usage
curl https://api.walletpress.cc/api/v1/x402/usage \
  -H "Authorization: Bearer $TOKEN"

# Response
{
  "tier": "pro",
  "free_generations_today": 47,
  "free_limit": 100,
  "paid_generations_today": 23,
  "next_reset": "2026-11-03T00:00:00Z"
}
```

---

## Payment Flow Details

### 1. Request Invoice

```bash
POST /api/v1/x402/wallet
Content-Type: application/json

{"chains": ["ethereum", "solana"], "label": "test"}
```

**Response (402):**

```json
{
  "error": "payment_required",
  "invoice": {
    "id": "inv_abc123def456",
    "amount_usd": 0.01,
    "amount_usdc": "0.01000000",
    "chain": "base",
    "recipient": "0x742d35Cc6634C0532925a3b8D4C0532925a3b8D4",
    "memo": "WalletPress wallet generation - inv_abc123def456",
    "expires_at": "2026-11-02T12:10:00Z",
    "payment_methods": ["usdc_base", "usdc_solana", "usdc_arbitrum", "usdc_ethereum"]
  }
}
```

### 2. Pay On-Chain

**Solana (via any wallet):**
```bash
# Using solana CLI
spl-token transfer \
  --fund-recipient \
  EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v \
  0.01 \
  0x742d35Cc6634C0532925a3b8D4C0532925a3b8D4 \
  --memo "inv_abc123def456"
```

**EVM (Base/Arbitrum/Ethereum):**
```bash
# Using cast (Foundry)
cast send 0x742d35Cc6634C0532925a3b8D4C0532925a3b8D4 \
  --value 0.01ether \
  --rpc-url https://mainnet.base.org \
  --private-key $PRIVATE_KEY \
  --data "0x$(echo -n 'inv_abc123def456' | xxd -p)"
```

### 3. Submit Payment Proof

```bash
curl -X POST https://api.walletpress.cc/api/v1/x402/wallet \
  -H "Content-Type: application/json" \
  -H "X-Payment: x402 eyJwcm9vZiI6I..." \
  -d '{"chains": ["ethereum", "solana"], "label": "my-wallet"}'
```

**Payment Proof Format (JWT):**

```json
{
  "header": { "alg": "ES256", "typ": "JWT" },
  "payload": {
    "invoice_id": "inv_abc123def456",
    "tx_hash": "0xabc123...",
    "chain": "base",
    "amount_usdc": "0.01000000",
    "paid_at": "2026-11-02T12:00:05Z",
    "payer": "0xYourAddress..."
  },
  "signature": "MEUCIQD..."
}
```

---

## Referral Revenue Sharing

Refer wallets, earn **20% of x402 fees** for 12 months.

```bash
# Get your referral link
curl https://api.walletpress.cc/api/v1/x402/referral \
  -H "Authorization: Bearer $TOKEN"

# Response
{
  "referral_code": "wp_ref_abc123",
  "referral_url": "https://walletpress.cc?ref=wp_ref_abc123",
  "commission_rate": "20%",
  "commission_duration_months": 12,
  "total_earned_usd": "47.32"
}
```

When someone uses your link and generates wallets via x402, you get 20% of the $0.01 fee automatically paid to your wallet.

---

## Integration for AI Agents

### Automatic 402 Handling

```python
from x402 import X402Client

# Client automatically handles 402 → pay → retry
client = X402Client(
    base_url="https://api.walletpress.cc",
    wallet=my_wallet,  # Private key or wallet client
    max_payment_usd=0.05,  # Safety cap
)

# Just call — payment handled transparently
wallet = await client.post("/api/v1/x402/wallet", json={
    "chains": ["ethereum", "solana"],
    "label": "agent-wallet-001"
})
```

### Budget Controls

```python
client = X402Client(
    base_url="https://api.walletpress.cc",
    wallet=my_wallet,
    max_payment_usd=0.10,      # Max per request
    daily_budget_usd=5.00,     # Max per day
    require_confirmation=True  # Pause for approval over threshold
)
```

---

## Transparency

- All payments on-chain, verifiable by anyone
- Invoices signed, tamper-proof
- Payment proofs stored with wallet records
- Arweave commitment for audit trail
- No trust required — verify yourself

```bash
# Verify a payment
curl https://api.walletpress.cc/api/v1/x402/verify \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tx_hash": "0xabc123...", "chain": "base"}'
```

---

## Next

- [x402 Wallet Generation →](x402/wallet-generation.md)
- [x402 Pricing →](x402/pricing.md)
- [x402 Integration →](x402/integration.md)
- [Referral Program →](x402/referral.md)
- [MCP Server →](../mcp/overview.md)
