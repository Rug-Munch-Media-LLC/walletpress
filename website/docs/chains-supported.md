---

title: "Chains Supported — 55 Blockchains, One Interface"
description: "Complete list of all 55 supported chains with derivation paths, address formats, and feature support matrix."
keywords: [chains, blockchains, bip44, derivation paths, ethereum, solana, bitcoin, cosmos, substrate]
unlisted: false
---



*Live — All 55 Chains Supported*

---

## Chain Registry

Every chain in WalletPress is defined in `CHAINS.yaml` — open-source, auditable, extensible. Each entry includes:
- Chain ID (CAIP-2 format)
- Name & ticker
- Derivation path (BIP44 coin type)
- Address format & validation
- RPC endpoints (primary + fallbacks)
- Explorer URLs
- Feature flags (token support, NFT support, etc.)

---

## EVM Chains (23)

Ethereum (ethereum), Arbitrum (arbitrum), Optimism (optimism), Base (base), Polygon (polygon), BNB Chain (bsc), Avalanche C-Chain (avalanche), Fantom (fantom), Gnosis (gnosis), Celo (celo), Polygon zkEVM (polygon-zkevm), Linea (linea), Mantle (mantle), Scroll (scroll), Zora (zora), Blast (blast), Mode (mode), Fraxtal (fraxtal), Metis (metis), Kava (kava), Moonbeam (moonbeam), Moonriver (moonriver), Cronos (cronos)

**Derivation:** `m/44'/60'/0'/0/0` (BIP44 coin type 60)
**Address:** 0x-prefixed, EIP-55 checksummed
**Tokens:** ERC-20, ERC-721, ERC-1155, ERC-4626, ERC-777
**NFTs:** ERC-721, ERC-1155

---

## Bitcoin & UTXO (3)

Bitcoin (bitcoin), Bitcoin Testnet (bitcoin-testnet), Bitcoin Cash (bitcoincash)

**Derivation:** `m/84'/0'/0'/0/0` (Native SegWit, BIP84)
**Address:** bc1q... (Bech32)
**Tokens:** Native BTC only (no token standard)

---

## Solana & SVM (2)

Solana (solana), Solana Devnet (solana-devnet)

**Derivation:** `m/44'/501'/0'/0'` (BIP44 coin type 501)
**Address:** Base58 (32-44 chars)
**Tokens:** SPL Token, SPL Token-2022
**NFTs:** Metaplex, Compressed NFTs

---

## Cosmos Ecosystem (8)

Cosmos Hub (cosmoshub), Osmosis (osmosis), Juno (juno), Injective (injective), Celestia (celestia), Neutron (neutron), Stride (stride), Axelar (axelar)

**Derivation:** `m/44'/118'/0'/0/0` (BIP44 coin type 118)
**Address:** bech32 (cosmos1...)
**Tokens:** CW20, IBC tokens
**Features:** IBC transfers, staking, governance

---

## Substrate / Polkadot (6)

Polkadot (polkadot), Kusama (kusama), Moonbeam (moonbeam), Moonriver (moonriver), Astar (astar), Substrate Generic (substrate)

**Derivation:** `m/44'/354'/0'/0/0` (BIP44 coin type 354)
**Address:** SS58 format (prefix-based)
**Tokens:** Native, ERC-20 (via Moonbeam), PSP22
**Features:** Parachain crowdloans, staking, XCM

---

## TRON (1)

TRON (tron)

**Derivation:** `m/44'/195'/0'/0/0` (BIP44 coin type 195)
**Address:** T... (Base58Check)
**Tokens:** TRC-10, TRC-20

---

## Ed25519 Chains (4)

Ed25519 Generic (ed25519), Cardano (cardano) — via Ed25519, Algorand (algorand) — via Ed25519, Stellar (stellar) — via Ed25519

**Derivation:** `m/44'/177'/0'/0/0` (Ed25519 generic)
**Key Type:** Ed25519 (not secp256k1)
**Address:** Chain-specific encoding

---

## Feature Support Matrix

| Chain      | Native Token | ERC-20/SPL  | NFTs | Staking | Governance | IBC/XCM  |
| ---------- | ------------ | ----------- | ---- | ------- | ---------- | -------- |
| Ethereum   | ✅           | ✅          | ✅   | ✅      | ✅         | —        |
| Arbitrum   | ✅           | ✅          | ✅   | ✅      | ✅         | —        |
| Solana     | ✅           | ✅          | ✅   | ✅      | ✅         | —        |
| Bitcoin    | ✅           | ❌          | ❌   | ❌      | ❌         | —        |
| Cosmos Hub | ✅           | ✅ (CW20)   | ✅   | ✅      | ✅         | ✅       |
| Polkadot   | ✅           | ✅ (PSP22)  | ✅   | ✅      | ✅         | ✅ (XCM) |
| TRON       | ✅           | ✅ (TRC-20) | ✅   | ✅      | ✅         | —        |

---

## Adding Custom Chains

```yaml
# CHAINS.yaml
custom_chain:
  caip2: "eip155:1337"
  name: "My Custom Chain"
  ticker: "CUSTOM"
  derivation_path: "m/44'/60'/0'/0/0"
  address_format: "eip55"
  rpc:
    - "https://rpc.customchain.com"
  explorer: "https://explorer.customchain.com"
  features:
    erc20: true
    erc721: true
    native_token: true
```

Then rebuild: `walletpress chains reload`

---

## Coin Type Reference

| Chain              | BIP44 Coin Type | Derivation Prefix |
| ------------------ | --------------- | ----------------- |
| Bitcoin            | 0               | m/84'/0'          |
| Ethereum (all EVM) | 60              | m/44'/60'         |
| Solana             | 501             | m/44'/501'        |
| Cosmos             | 118             | m/44'/118'        |
| Polkadot           | 354             | m/44'/354'        |
| TRON               | 195             | m/44'/195'        |
| Ed25519 generic    | 177             | m/44'/177'        |
| Cardano            | 1815            | m/44'/1815'       |

---

## Next

- [API Reference →](../api/wallet-generation.md)
- [Security Model →](../security/overview.md)
- [Adding Custom Chains →](development/adding-chains.md)
