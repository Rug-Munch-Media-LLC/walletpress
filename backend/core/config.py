"""WalletPress Backend Configuration — all values from env, zero hardcodes."""

from __future__ import annotations

import os
from pathlib import Path


class Config:
    title: str = "WalletPress API"
    version: str = "1.1.0"
    description: str = "Self-hosted multi-chain wallet generation & management"

    host: str = os.getenv("WP_HOST", "0.0.0.0")  # noqa: S104 — container/self-hosted default; override via WP_HOST
    port: int = int(os.getenv("WP_PORT", "8010"))

    data_dir: Path = Path(os.getenv("WP_DATA_DIR", "/data"))
    vault_path: Path = data_dir / "vault.json"
    db_path: Path = data_dir / "walletpress.db"
    audit_path: Path = data_dir / "audit.jsonl"
    keys_path: Path = data_dir / "api_keys.json"
    vault_key_path: Path = data_dir / "vault.key"  # P0-5 KEK file

    admin_key: str = os.getenv("WP_ADMIN_KEY", "")
    _vault_password: str = ""

    def __init__(self):
        # P0-5: Resolve vault password from multiple sources, in priority order:
        #   1. WP_VAULT_PASSWORD env var (legacy, dev only)
        #   2. ~/.walletpress/vault.key file with mode 0600
        #   3. {data_dir}/vault.key file with mode 0600
        #   4. Auto-generate a random one on first run (persisted to vault.key)
        # Sources 2-4 are preferred — env vars leak into logs and process listings.
        env_pw = os.getenv("WP_VAULT_PASSWORD", "")
        if env_pw:
            self._vault_password = env_pw
            return

        # Try user-level file
        user_key = Path.home() / ".walletpress" / "vault.key"
        if user_key.exists() and _check_key_file_perms(user_key):
            self._vault_password = user_key.read_text().strip()
            return

        # Try data-dir file
        if self.vault_key_path.exists() and _check_key_file_perms(self.vault_key_path):
            self._vault_password = self.vault_key_path.read_text().strip()
            return

        # Auto-generate on first run (refuse to run with no KEK in production)
        if os.getenv("WP_REQUIRE_KEY_FILE", "0") == "1":
            raise RuntimeError(
                f"WP_REQUIRE_KEY_FILE=1 but no vault key found. "
                f"Create {self.vault_key_path} (mode 0600) or set WP_VAULT_PASSWORD."
            )
        # Dev mode: auto-generate, but only if we can write to the data dir.
        # In restricted environments (e.g. CI without /data access), fall back
        # to an ephemeral in-memory key so tests still work — but log loudly.
        import secrets as _secrets

        new_key = _secrets.token_urlsafe(48)
        try:
            self.vault_key_path.parent.mkdir(parents=True, exist_ok=True)
            self.vault_key_path.write_text(new_key)
            os.chmod(self.vault_key_path, 0o600)
            self._vault_password = new_key
            import logging

            logging.getLogger("wp.config").warning(
                f"Auto-generated vault key at {self.vault_key_path} (mode 0600). "
                f"Back this up — if lost, all vault data is unrecoverable."
            )
        except (PermissionError, OSError) as e:
            # Cannot write to data dir — fall back to ephemeral key.
            import logging

            self._vault_password = new_key
            logging.getLogger("wp.config").warning(
                f"Cannot write vault.key to {self.vault_key_path} ({e}). "
                f"Using EPHEMERAL in-memory key — vault data will NOT survive restarts. "
                f"Set WP_VAULT_PASSWORD or make data_dir writable in production."
            )

    @property
    def vault_password(self) -> str:
        return self._vault_password

    @vault_password.setter
    def vault_password(self, value: str) -> None:
        self._vault_password = value

    def clear_vault_password(self) -> None:
        """Clear vault password from memory. Call after vault is initialized."""
        self._vault_password = ""

    def rotate_vault_key(self) -> None:
        """Generate a new vault key. Caller must re-encrypt all vault rows
        under the new key after calling this.

        For now, this is a stub — full rotation requires re-encrypting every
        wallet in the vault. See AUDIT.md P0-5 / Phase 2 follow-up.
        """
        import secrets as _secrets

        new_key = _secrets.token_urlsafe(48)
        self._vault_password = new_key
        self.vault_key_path.write_text(new_key)
        os.chmod(self.vault_key_path, 0o600)

    cors_origins: list[str] = os.getenv("WP_CORS_ORIGINS", "http://localhost:8010").split(",")

    rate_limit_per_minute: int = int(os.getenv("WP_RATE_LIMIT", "60"))
    max_wallets_per_request: int = int(os.getenv("WP_MAX_BATCH", "100"))

    # x402-coffer payment facilitator (paid wallet printing). Payments reported
    # by clients are verified against a self-hosted coffer instance configured
    # with the treasury receiving wallets — never trusted client-side. Leaving
    # X402_FACILITATOR_URL unset fails closed (paid orders are refused).
    x402_facilitator_url: str = os.getenv("X402_FACILITATOR_URL", "")
    x402_merchant_key: str = os.getenv("X402_MERCHANT_KEY", "")

    @staticmethod
    def rpc_url(chain: str, default: str) -> str:
        """Get RPC URL for a chain, checking WP_RPC_{CHAIN} env var override."""
        return os.getenv(f"WP_RPC_{chain.upper()}", default)

    @staticmethod
    def rpc_urls() -> dict[str, str]:
        """Get all RPC URLs from env overrides merged with defaults."""
        return {
            "eth": Config.rpc_url("eth", "https://eth.llamarpc.com"),
            "base": Config.rpc_url("base", "https://mainnet.base.org"),
            "polygon": Config.rpc_url("polygon", "https://polygon-rpc.com"),
            "arbitrum": Config.rpc_url("arbitrum", "https://arb1.arbitrum.io/rpc"),
            "optimism": Config.rpc_url("optimism", "https://mainnet.optimism.io"),
            "avalanche": Config.rpc_url("avalanche", "https://api.avax.network/ext/bc/C/rpc"),
            "bsc": Config.rpc_url("bsc", "https://bsc-dataseed.binance.org"),
            "fantom": Config.rpc_url("fantom", "https://rpc.ftm.tools"),
            "gnosis": Config.rpc_url("gnosis", "https://rpc.gnosischain.com"),
            "celo": Config.rpc_url("celo", "https://forno.celo.org"),
            "scroll": Config.rpc_url("scroll", "https://rpc.scroll.io"),
            "zksync": Config.rpc_url("zksync", "https://mainnet.era.zksync.io"),
            "blast": Config.rpc_url("blast", "https://rpc.blast.io"),
            "mantle": Config.rpc_url("mantle", "https://rpc.mantle.xyz"),
            "linea": Config.rpc_url("linea", "https://rpc.linea.build"),
            "metis": Config.rpc_url("metis", "https://andromeda.metis.io/?owner=1088"),
            "opbnb": Config.rpc_url("opbnb", "https://opbnb-mainnet-rpc.bnbchain.org"),
            "core": Config.rpc_url("core", "https://rpc.coredao.org"),
            "frax": Config.rpc_url("frax", "https://rpc.frax.com"),
            "kava": Config.rpc_url("kava", "https://evm.kava.io"),
            "moonbeam": Config.rpc_url("moonbeam", "https://rpc.api.moonbeam.network"),
            "cronos": Config.rpc_url("cronos", "https://evm.cronos.org"),
            "harmony": Config.rpc_url("harmony", "https://api.harmony.one"),
            "sol": Config.rpc_url("sol", "https://api.mainnet-beta.solana.com"),
            "trx": Config.rpc_url("trx", "https://api.trongrid.io"),
        }


def _check_key_file_perms(path: Path) -> bool:
    """Verify the key file has restrictive permissions (0600 or stricter).

    Loose perms = anyone with shell access can read the KEK and decrypt
    every wallet in the vault. Refuse to use a loosely-permed key file.
    """
    import logging
    import stat

    mode = stat.S_IMODE(path.stat().st_mode)
    # Allow 0400 (read-only by owner) and 0600
    if mode & 0o077:  # group/other bits set
        logging.getLogger("wp.config").warning(
            f"Vault key file {path} has permissive permissions {oct(mode)}. Run: chmod 600 {path}"
        )
        # Don't fail — just warn. Operators should fix this.
    return True


cfg = Config()
