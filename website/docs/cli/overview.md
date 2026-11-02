---

title: "CLI — WalletPress in Your Terminal"
description: "Full wallet operations from command line. Generate, derive, sign, manage. Scriptable, automatable, no API keys needed for local vault access."
keywords: [cli, command line, walletpress, terminal, automation, scripting, wallet management]
unlisted: false
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';


**Live**

**Full wallet operations from your terminal. Scriptable, automatable, local vault access without API keys.**

---

## Install

```bash
# Linux/macOS (binary)
curl -L https://github.com/RugMunchMedia/walletpress/releases/latest/download/walletpress-$(uname -s)-$(uname -m) -o walletpress
chmod +x walletpress
sudo mv walletpress /usr/local/bin/

# macOS (Homebrew)
brew tap rugmunchmedia/walletpress
brew install walletpress

# Docker
docker run --rm -it walletpress/walletpress:latest walletpress --help

# Cargo (from source)
cargo install --git https://git.example.com/RugMunchMedia/walletpress.git walletpress-cli
```

---

## Configuration

### Config File

```yaml
# ~/.config/walletpress/config.yaml
vault:
  path: ~/.walletpress/vault.db
  key_env: VAULT_KEY # or key_file: ~/.walletpress/vault.key

api:
  endpoint: http://localhost:8010
  timeout: 30s

mcp:
  endpoint: http://localhost:8010/mcp/sse

output:
  format: table # table, json, yaml, csv
  colors: true

chains:
  default: ["ethereum", "solana", "bitcoin"]
  derivation_path: "m/44'/60'/0'/0/0"
```

### Environment Variables

```bash
export VAULT_KEY="$(cat ~/.walletpress/vault.key)"  # 32-byte base64
export WALLETPRESS_CONFIG="/custom/path/config.yaml"
export WALLETPRESS_VAULT_PATH="/custom/path/vault.db"
```

---

## Commands

### Wallet Generation

```bash
# Generate wallet for default chains
walletpress generate

# Generate for specific chains
walletpress generate --chains ethereum,solana,bitcoin,polygon

# Generate with label
walletpress generate --label "trading-bot-001"

# Generate with custom derivation path
walletpress generate --derivation-path "m/44'/60'/0'/0/0"

# Generate from existing mnemonic (restore)
walletpress generate --mnemonic "abandon abandon abandon..."

# Generate with passphrase
walletpress generate --passphrase "my-bip39-passphrase"

# Output as JSON for scripting
walletpress generate --chains ethereum,solana --format json
```

**Output (table):**

```
┌─────────────────────────────────────────────────────────────────┐
│ Wallet Generated: wlt_abc123def456                              │
├──────────────┬──────────────────────────────────────────────────┤
│ Label        │ trading-bot-001                                   │
│ Chains       │ ethereum, solana, bitcoin, polygon                │
│ Derivation   │ m/44'/60'/0'/0/0                                  │
│ Mnemonic     │ abandon abandon abandon abandon abandon abandon  │
│              │ abandon abandon abandon abandon abandon abandon  │
│              │ about                                             │
├──────────────┼──────────────────────────────────────────────────┤
│ ethereum     │ 0x742d35Cc6634C0532925a3b8D4C0532925a3b8D4       │
│ solana       │ 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU     │
│ bitcoin      │ bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh        │
│ polygon      │ 0x742d35Cc6634C0532925a3b8D4C0532925a3b8D4       │
├──────────────┼──────────────────────────────────────────────────┤
│ Arweave Proof│ https://arweave.net/abc123def456                  │
│ Created      │ 2026-11-02T12:00:00Z                              │
└──────────────┴──────────────────────────────────────────────────┘
```

---

### Wallet Management

```bash
# List all wallets
walletpress list

# List with filters
walletpress list --chain ethereum --label trading --format json

# Get wallet details
walletpress get wlt_abc123def456

# Update wallet label
walletpress update wlt_abc123def456 --label "new-label"

# Soft delete (preserves vault data)
walletpress delete wlt_abc123def456

# Purge (irreversible — requires confirmation)
walletpress purge wlt_abc123def456 --confirm
```

---

### Address Derivation

```bash
# Derive single address
walletpress derive wlt_abc123def456 --chain ethereum --path "m/44'/60'/0'/0/5"

# Derive batch
walletpress derive-batch wlt_abc123def456 --chain ethereum --start 0 --count 20 --label-prefix "deposit-"

# List all addresses for wallet
walletpress addresses wlt_abc123def456 --chain ethereum
```

---

### Signing

```bash
# Sign transaction (Ethereum)
walletpress sign-tx wlt_abc123def456 \
  --chain ethereum \
  --path "m/44'/60'/0'/0/0" \
  --tx '{"to":"0x742d35...","value":"1000000000000000000","gas":"21000","gasPrice":"20000000000","nonce":0,"chainId":1}'

# Sign message (EIP-191)
walletpress sign-msg wlt_abc123def456 \
  --chain ethereum \
  --path "m/44'/60'/0'/0/0" \
  --message "Hello, WalletPress!"

# Sign typed data (EIP-712)
walletpress sign-typed wlt_abc123def456 \
  --chain ethereum \
  --path "m/44'/60'/0'/0/0" \
  --data '{"domain":{"name":"Test","version":"1"},"types":{"Person":[{"name":"name","type":"string"}]},"primaryType":"Person","message":{"name":"Alice"}}'
```

---

### x402 Operations

```bash
# Generate wallet via x402 (pay per use)
walletpress x402 generate --chains ethereum,solana --label "x402-wallet"

# Check x402 balance/usage
walletpress x402 usage
```

---

### Utility

```bash
# Health check
walletpress health

# Verify Arweave proof
walletpress verify-proof wlt_abc123def456

# Export wallet (encrypted)
walletpress export wlt_abc123def456 --output wallet-backup.enc --password "strong-password"

# Import wallet
walletpress import wallet-backup.enc --password "strong-password"

# Vault management
walletpress vault status
walletpress vault seal          # Emergency seal
walletpress vault unseal        # Requires VAULT_KEY

# Audit log
walletpress audit --since 2026-11-01 --format json
```

---

## Scripting Examples

### Batch Wallet Generation

```bash
#!/bin/bash
# generate-wallets.sh - Generate 100 wallets for airdrop

for i in {1..100}; do
  walletpress generate \
    --chains ethereum,solana \
    --label "airdrop-$i" \
    --format json >> airdrop-wallets.json
  
  # Rate limit
  sleep 0.1
done

# Extract addresses for distribution
jq -r '.chains.ethereum.address' airdrop-wallets.json > ethereum-addresses.txt
jq -r '.chains.solana.address' airdrop-wallets.json > solana-addresses.txt
```

### Automated Trading Bot Setup

```bash
#!/bin/bash
# setup-trading-bot.sh

WALLET_ID=$(walletpress generate \
  --chains ethereum,arbitrum,optimism,base \
  --label "trading-bot-main" \
  --format json | jq -r '.id')

# Derive deposit addresses
for i in {0..9}; do
  walletpress derive $WALLET_ID \
    --chain ethereum \
    --path "m/44'/60'/0'/0/$i" \
    --label "deposit-$i" \
    --format json >> deposit-addresses.json
done

echo "Trading bot wallet: $WALLET_ID"
echo "Deposit addresses saved to deposit-addresses.json"
```

### CI/CD Integration

```yaml
# .github/workflows/deploy.yml
- name: Generate deployment wallet
  run: |
    WALLET=$(walletpress generate --chains ethereum --label "deploy-${{ github.sha }}" --format json)
    ADDRESS=$(echo $WALLET | jq -r '.chains.ethereum.address')
    echo "DEPLOY_ADDRESS=$ADDRESS" >> $GITHUB_ENV
```

---

## Configuration Reference

```yaml
# Full config.yaml reference
vault:
  path: ~/.walletpress/vault.db
  key_env: VAULT_KEY
  key_file: ~/.walletpress/vault.key
  auto_seal_timeout: 3600 # seconds of inactivity

api:
  endpoint: http://localhost:8010
  timeout: 30s
  rate_limit: 100 # req/s

mcp:
  endpoint: http://localhost:8010/mcp/sse
  auth_token_env: MCP_AUTH_TOKEN

output:
  format: table # table, json, yaml, csv
  colors: true
  pager: true

chains:
  default: ["ethereum", "solana", "bitcoin"]
  derivation_path: "m/44'/60'/0'/0/0"

logging:
  level: info # debug, info, warn, error
  file: ~/.walletpress/logs/walletpress.log
  max_size: 100MB
  max_files: 10
```

---

## Shell Completion

```bash
# Bash
walletpress completion bash > /etc/bash_completion.d/walletpress

# Zsh
walletpress completion zsh > ~/.zsh/completions/_walletpress

# Fish
walletpress completion fish > ~/.config/fish/completions/walletpress.fish

# PowerShell
walletpress completion powershell > walletpress.ps1
```

---

## Troubleshooting

| Issue                | Fix                                                              |
| -------------------- | ---------------------------------------------------------------- |
| `vault: locked`      | Run `walletpress vault unseal` with VAULT_KEY                    |
| `vault: not found`   | Check `vault.path` in config, run `walletpress generate` to init |
| `connection refused` | Ensure API server running on `api.endpoint`                      |
| `permission denied`  | Check file permissions on vault.db and config.yaml               |
| `invalid mnemonic`   | Ensure 12/24 words, correct wordlist (BIP39 English)             |

---

## Next

- [REST API Reference →](../api/wallet-generation.md)
- [MCP Server →](../mcp/overview.md)
- [Deployment →](../deployment/self-hosted.md)
- [Security Model →](../security/overview.md)
