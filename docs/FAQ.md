# WalletPress — FAQ

**What is WalletPress?** A wallet management engine: FastAPI backend + WordPress plugin for wallet connect, tracking, and web3 user features.

**Do I need both parts?** The backend runs standalone; the WordPress plugin is the CMS integration layer.

**Which chains?** EVM + Solana wallet connect; extend via connector modules.

**How do secrets work?** Env-injected at runtime (`backend/.env.example` documents names); WordPress side uses options stored server-side.

**Is there a demo flow?** See docs/adr/0001 for architecture and DEVELOPMENT.md for local setup.
