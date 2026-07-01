=== WalletPress ===
Contributors: rugmunch
Tags: crypto, wallet, blockchain, token-gate, web3, metamask, phantom, solana, ethereum, nft, defi
Requires at least: 6.0
Tested up to: 6.7
Stable tag: 1.0.0-beta
Requires PHP: 8.1
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Self-hosted wallet management platform. Generate, vault, analyze, and gate content with crypto wallets across 55 blockchains.

== Description ==

WalletPress is a self-hosted wallet management platform that brings the full power of your multi-chain crypto backend into WordPress. It is a **developer product first** — you deploy the backend, configure the plugin, and unlock enterprise-grade wallet infrastructure with a clean admin UI.

= Features =

* **Wallet Vault** — Browse, export, and manage HD wallets across 55 chains (Solana, Ethereum, Base, Polygon, BSC, Arbitrum, Avalanche, Optimism, zkSync, Scroll, Blast, Mantle, Linea, opBNB, Manta, Polygon zkEVM, StarkNet, Sui, Aptos, Bitcoin, Litecoin, Dogecoin, Cosmos, Polkadot, Kusama, TRON, and more)
* **Wallet Generation** — Generate single wallets, batch wallets, or full-chain sweeps with BIP39, BIP32, BIP44, BIP49, BIP84, BIP86 derivation
* **Wallet Analysis** — Check balances, analyze transaction history, scan for risk, and verify signatures
* **Mnemonic Converter** — Convert a BIP39 mnemonic phrase to addresses on all supported chains instantly
* **Token Gating** — Lock any content behind token/NFT ownership with simple shortcodes `[wallet_gate id="1"]`
* **Crypto Payments** — Accept SOL, ETH, MATIC, BNB, and ERC-20/BEP-20/SPL tokens. Users connect their wallet and pay with one click
* **Wallet Login** — MetaMask EIP-1193 and Phantom wallet Connect button with nonce-based signature verification. Auto-creates WP users
* **RBAC** — Role-based API key permissions with granular scopes
* **API Keys** — Generate, list, rotate, and revoke API keys with scope-limited access
* **Webhooks** — Create webhooks for wallet.generated, wallet.swept, payment.received, gate.verified events
* **Audit Trail** — Full audit log of all wallet operations
* **Balance Snapshots** — Periodic balance tracking with history viewer
* **Sweep & Rotate** — Sweep funds to a destination address, rotate wallet keys, or create temporal (TTL-expiring) wallets
* **Paper Wallets** — Generate paper wallet PDFs with QR codes
* **Admin Dashboard** — 15 admin pages covering every feature

= Supported Chains =

Solana, Ethereum, Base, Polygon, BSC, Arbitrum, Avalanche, Optimism, zkSync, Scroll, Blast, Mantle, Linea, opBNB, Manta, Polygon zkEVM, StarkNet, Sui, Aptos, Neon, Near, Aurora, Celo, Moonbeam, Moonriver, Fantom, Cronos, Gnosis, Telos

== Installation ==

1. Upload the `walletpress` folder to `/wp-content/plugins/`
2. Activate the plugin through the Plugins screen
3. Go to **WalletPress → Setup** in your WP admin
4. Enter your backend API URL and API key
5. Configure your merchant wallet address and default chain
6. Start generating wallets, creating token gates, and accepting payments

= Backend Requirements =

WalletPress requires a running instance of the `rmi-backend` API. See the Deployment Guide at `docs/DEPLOYMENT.md` for setup instructions. The backend provides:

* REST API at `/api/v1/chain-vault` and `/api/v1/wallet`
* 86+ endpoints covering all wallet operations
* Postgres + Redis + ClickHouse storage
* Optional: Reth (archive node), Neo4j (entity graphs), Qdrant (vector memory)

== Frequently Asked Questions ==

= Do I need a third-party service? =

No. WalletPress is self-hosted. You deploy the backend on your own infrastructure. No monthly SaaS fees, no API usage limits.

= How do users connect their wallets? =

Frontend includes MetaMask (EIP-1193) and Phantom connectors. The Connect button generates a nonce, the user signs it with their wallet, and the server verifies the signature. This creates/authenticates a WP user account.

= What happens to existing users? =

Existing WP users can link a wallet address in their profile. Wallet-authenticated users get auto-registered as WP users with the role you configure.

= Can I sell access to content? =

Yes. The Token Gating shortcode locks content behind token/NFT ownership. Combined with Crypto Payments, users can purchase access and automatically unlock gated content.

= Is the plugin compatible with other page builders? =

Yes. The `[wallet_gate]` shortcode works in Classic Editor, Gutenberg, Elementor, WPBakery, and any builder that supports shortcodes.

== Screenshots ==

1. WalletPress Admin Dashboard — overview of vault, gates, payments, and system health
2. Wallet Vault — browse all wallets across chains with search and filter
3. Wallet Generation — generate single or batch wallets with label/chain options
4. Token Gates — create and manage token/NFT gating rules
5. Crypto Payments — configure payment form and view transaction history
6. Settings — API connection, merchant wallet, chain defaults

== Changelog ==

= 1.0.0-beta =
* Initial beta release
* Wallet vault with 55 chains
* Wallet generation (single, batch, full sweep)
* Mnemonic to addresses converter
* Token gating with shortcode
* Crypto payments with wallet connection
* MetaMask/Phantom wallet login
* API key management with scopes
* Webhook creation and management
* Audit trail viewer
* Balance snapshots and history
* 15 admin pages

== Upgrade Notice ==

= 1.0.0-beta =
First beta release. Test thoroughly before production use.
