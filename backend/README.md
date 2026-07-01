# WalletPress

Multi-chain wallet generation engine supporting 55 blockchains.
MIT open source. BIP39/BIP32/BIP44 compatible.

## What It Does

Generates cryptographically secure wallets on 55 chains from a single API.
Each wallet is a full keypair — private key, public key, address — on your
choice of blockchain. Keys are derived from CSPRNG entropy per BIP39 standards
and can optionally be derived deterministically from a mnemonic phrase.

## Requirements

- Python 3.10+ (3.12 recommended)
- OpenSSL 3.x (for Argon2id encryption)
- SQLite 3.37+ (WAL mode)
- 1GB RAM minimum (4GB recommended for vault > 10,000 wallets)

## Build & Run

```bash
# Dependencies vary by OS. You'll need python3-dev, libssl-dev, build-essential.
# Platform-specific package names are not documented here.

pip install -r requirements.txt

# Generate credentials yourself:
# WP_ADMIN_KEY — 32+ byte hex string for API authentication
# WP_VAULT_PASSWORD — 20+ char passphrase for AES-256-GCM key encryption
# These have no defaults. The server will not start without them.

export WP_ADMIN_KEY=<your 32+ byte hex key>
export WP_VAULT_PASSWORD=<your 20+ char passphrase>

python main.py
```

## API

Docs at `http://localhost:8010/docs` when running.

## WordPress Plugin

See `wp-plugin/`. Requires a running WalletPress backend.

## Test Vectors

```bash
python scripts/verify_test_vectors.py
```

## License

MIT — the code is free. Making it work in production is your responsibility.

---

**walletpress.cc** — one-command deploy, pre-configured RPC, SSL, backups, monitoring.
Or use the hosted version at walletpress.cc/app — zero setup, $29/mo.
