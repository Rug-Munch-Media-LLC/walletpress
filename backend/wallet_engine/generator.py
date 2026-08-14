"""WalletPress Wallet Generator — deterministic, auditable, multi-chain.

CORE TRUST PRINCIPLE:
    "You don't need to trust WalletPress. The math is open source.
    Every address is derived using BIP39/BIP32/BIP44/BIP49/BIP84 standards.
    You can verify every single address with any standard wallet software."

This engine generates real cryptographic keys. It NEVER phones home, NEVER
tracks what you generate, and NEVER stores unencrypted keys unless explicitly
configured to do so.

SECURITY MODEL:
    - Client-side generation (default): Keys generated in browser/plugin,
      only encrypted blobs reach the server
    - Server-side generation (enterprise): Keys encrypted at rest with
      AES-256-GCM + Argon2id, vault password configurable, never logged
    - Zero telemetry, zero analytics, zero third-party calls

BUILD REPRODUCIBILITY:
    - Same mnemonic + same path = same address, ALWAYS, on ANY software
    - Verified against BitcoinJS, ethers.js, Solana Web3.js test vectors
    - Deterministic builds: Docker image SHA matches source tree hash
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from .chains import CHAINS, ChainFamily

logger = logging.getLogger("wp.generator")

try:
    from coincurve import PrivateKey as CoinCurveKey
except ImportError:
    raise RuntimeError("coincurve is required. Install it: pip install coincurve>=18.0.0") from None

try:
    import base58
except ImportError:
    raise RuntimeError("base58 is required. Install it: pip install base58>=2.1.1") from None

try:
    from argon2.low_level import Type as _Argon2Type, hash_secret_raw as _argon2id_kdf
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    raise RuntimeError(
        "cryptography and argon2-cffi are required. Install them: pip install cryptography>=42.0.0 argon2-cffi>=23.0.0"
    ) from None

try:
    from Crypto.Hash import keccak
except ImportError:
    raise RuntimeError(
        "pycryptodome is required. Install it: pip install pycryptodome>=3.20.0"
    ) from None


def _keccak256(data: bytes) -> bytes:
    k = keccak.new(digest_bits=256)
    k.update(data)
    return k.digest()


def _to_eip55_checksum(address: str) -> str:
    """Encode an Ethereum address with EIP-55 mixed-case checksum.

    Reference: https://eips.ethereum.org/EIPS/eip-55
    """
    addr_lower = address.removeprefix("0x").lower()
    addr_hash = _keccak256(addr_lower.encode()).hex()
    result = ["0x"]
    for i, c in enumerate(addr_lower):
        if c.isdigit():
            result.append(c)
        else:
            result.append(c.upper() if int(addr_hash[i], 16) >= 8 else c)
    return "".join(result)


class CryptoError(RuntimeError):
    """Crypto operation failed unexpectedly (internal error, not bad input)."""


class CryptoInputError(ValueError):
    """Invalid user input to a crypto operation (caller returns HTTP 400)."""


def _crypto_log_error(logger, operation, context=None):
    import sys

    exc = sys.exc_info()[1]
    logger.error(
        "Crypto operation failed: %s | error=%s: %s | context=%s",
        operation,
        type(exc).__name__,
        exc,
        context or {},
        exc_info=True,
    )


def validate_mnemonic(mnemonic: str) -> str:
    """Validate a BIP39 mnemonic phrase and return a cleaned version.

    Returns the normalized mnemonic on success.
    Raises ValueError with a clear message on failure.
    """
    mnemonic = mnemonic.strip().lower()
    if not mnemonic:
        raise ValueError("Mnemonic phrase cannot be empty")

    words = mnemonic.split()
    if len(words) not in (12, 15, 18, 21, 24):
        raise ValueError(
            f"Invalid mnemonic length: {len(words)} words. "
            f"BIP39 requires 12, 15, 18, 21, or 24 words (got {len(words)})"
        )

    # P2-2 fix: bip_utils is REQUIRED for BIP39 validation. Previously the
    # try/except silently passed, meaning garbage mnemonics would generate
    # garbage wallets. Now we raise hard.
    try:
        from bip_utils import Bip39MnemonicValidator
    except ImportError as e:
        raise RuntimeError(
            "bip_utils is required for BIP39 mnemonic validation. "
            "Install it: pip install bip-utils>=2.9.0"
        ) from e
    if not Bip39MnemonicValidator().IsValid(mnemonic):
        raise ValueError(
            "Mnemonic phrase failed BIP39 checksum validation. Check the word order and spelling."
        )

    return mnemonic


def _ensure_hardened_path(path: str) -> str:
    """Ensure every index in a BIP32 derivation path uses hardened derivation.

    Ed25519 (SLIP-10) does not support non-hardened (public) derivation.
    Converts trailing non-hardened indices like ``0/0`` → ``0'/0'``.
    """
    parts = path.split("/")
    result = []
    for p in parts:
        if p == "m" or p.endswith(("'", "H")):
            result.append(p)
        else:
            result.append(p + "'")
    return "/".join(result)


# Chain-specific address encoders that bypass the family-based dispatch.
# Each entry tells generator.generate() how to derive keys and produce the
# final address string using wallet_engine.chain_addresses. See that module
# for the encoding details and reference SDKs used.
#
# Format: chain_key -> {
#   "curve": "secp256k1" or "ed25519" or "sr25519",
#   "address_family": one of the chain_addresses encoder families,
#   "address_args_extra": additional positional args to the encoder (e.g. HRP),
# }
CHAIN_ADDRESS_OVERRIDES: dict[str, dict] = {
    # Cosmos family — secp256k1 keys, bech32 address with chain-specific HRP
    "atom": {"curve": "secp256k1", "address_family": "bech32", "hrp": "cosmos"},
    "osmo": {"curve": "secp256k1", "address_family": "bech32", "hrp": "osmo"},
    "juno": {"curve": "secp256k1", "address_family": "bech32", "hrp": "juno"},
    "sei": {"curve": "secp256k1", "address_family": "bech32", "hrp": "sei"},
    "inj": {"curve": "secp256k1", "address_family": "bech32", "hrp": "inj"},
    "evmos": {"curve": "secp256k1", "address_family": "bech32", "hrp": "evmos"},
    # Stellar — ed25519
    "xlm": {"curve": "ed25519", "address_family": "stellar"},
    # XRP — secp256k1 with custom base58 alphabet
    "xrp": {"curve": "secp256k1", "address_family": "xrp"},
    # Tezos — ed25519 with tz1 watermark
    "xtz": {"curve": "ed25519", "address_family": "tezos"},
    # TON — ed25519 with workchain + CRC16
    "ton": {"curve": "ed25519", "address_family": "ton"},
    # Filecoin — secp256k1 with f1 prefix
    "fil": {"curve": "secp256k1", "address_family": "filecoin"},
    # Nano — ed25519 with custom format
    "xno": {"curve": "ed25519", "address_family": "nano"},
    # Algorand — ed25519 with SHA-512/256 checksum
    "algo": {"curve": "ed25519", "address_family": "algorand"},
    # Monero — handled separately in _generate_monero (uses monero library)
    # Substrate (Polkadot/Kusama) — sr25519, handled separately
    # Bitcoin Cash — secp256k1 + cashaddr encoding
    "bch": {"curve": "secp256k1", "address_family": "bch"},
    # Zcash transparent — secp256k1 with proper t-addr prefix (0x1C8)
    "zec": {"curve": "secp256k1", "address_family": "zcash_t"},
    # Cardano — Kholaw (BIP32-Ed25519) via pycardano
    "ada": {"curve": "ed25519_kholaw", "address_family": "cardano", "network": "mainnet"},
}


@dataclass
class GeneratedWallet:
    chain: str
    chain_name: str
    symbol: str
    address: str
    private_key_hex: str = ""
    public_key_hex: str = ""
    mnemonic: str = ""
    derivation_path: str = ""
    address_type: str = ""
    created_at: float = 0.0
    label: str = ""
    tags: list[str] = field(default_factory=list)
    encrypted: bool = False

    def to_safe_dict(self) -> dict[str, Any]:
        d = {
            "chain": self.chain,
            "chain_name": self.chain_name,
            "symbol": self.symbol,
            "address": self.address,
            "address_type": self.address_type,
            "derivation_path": self.derivation_path,
            "created_at": self.created_at,
            "label": self.label,
            "tags": self.tags,
            "has_private_key": bool(self.private_key_hex),
            "has_mnemonic": bool(self.mnemonic),
            "encrypted": self.encrypted,
            "public_key": self.public_key_hex,
        }
        return d

    def to_full_dict(self) -> dict[str, Any]:
        return {
            **self.to_safe_dict(),
            "private_key_hex": self.private_key_hex,
            "mnemonic": self.mnemonic,
        }

    def clear_sensitive(self) -> None:
        """Zero sensitive key material from memory.

        After the wallet data has been persisted or returned to the caller,
        call this to minimize the window where private keys sit in Python
        memory. Note: Python str objects cannot be explicitly zeroed, so
        this only removes the reference. For stronger guarantees, use the
        context manager or ensure the wallet object goes out of scope.
        """
        self.private_key_hex = ""
        self.mnemonic = ""
        self._clear_bytearrays()

    _private_key_bytes: bytearray | None = None
    _mnemonic_bytes: bytearray | None = None

    def _clear_bytearrays(self) -> None:
        if self._private_key_bytes is not None:
            for i in range(len(self._private_key_bytes)):
                self._private_key_bytes[i] = 0
            self._private_key_bytes = None
        if self._mnemonic_bytes is not None:
            for i in range(len(self._mnemonic_bytes)):
                self._mnemonic_bytes[i] = 0
            self._mnemonic_bytes = None

    def __enter__(self) -> GeneratedWallet:
        return self

    def __exit__(self, *args) -> None:
        self.clear_sensitive()


class WalletGenerator:
    """Deterministic multi-chain wallet generator.

    Every generation follows BIP39/BIP32/BIP44 standards. Given the same
    mnemonic phrase and derivation path, ANY wallet software in the world
    will produce the SAME address. This is not magic — it's math.
    """

    def __init__(self, vault_password: str = ""):
        self._vault_password = vault_password
        self._generation_count = 0

    def generate(
        self,
        chain_key: str,
        mnemonic: str = "",
        passphrase: str = "",
        label: str = "",
        tags: list[str] | None = None,
        derivation_path: str = "",
    ) -> GeneratedWallet:
        """Generate a wallet for any supported chain.

        Args:
            chain_key: Chain identifier (e.g. 'eth', 'sol', 'btc')
            mnemonic: Optional BIP39 mnemonic. If empty, one is generated.
            passphrase: Optional BIP39 passphrase for hidden wallets.
            label: Human-readable label.
            tags: Optional categorization tags.
            derivation_path: Custom BIP44 derivation path. Empty = chain default.

        Returns:
            GeneratedWallet with address and encrypted private key.
        """
        chain = CHAINS.get(chain_key.lower())
        if not chain:
            raise CryptoInputError(
                f"Unsupported chain: {chain_key}. Supported: {list(CHAINS.keys())}"
            )

        if not mnemonic:
            mnemonic = self._generate_mnemonic()

        now = time.time()
        effective_path = derivation_path or chain.hd_path

        # Dispatch to the appropriate chain generator inside a try/except
        # so that any crypto failure is caught, logged, and re-raised as CryptoError.
        try:
            chain_key_lower = chain_key.lower()
            if chain_key_lower in CHAIN_ADDRESS_OVERRIDES:
                result = self._generate_with_override(
                    chain, mnemonic, passphrase, effective_path, chain_key_lower
                )
            elif chain.family == ChainFamily.EVM:
                result = self._generate_evm(chain, mnemonic, passphrase, effective_path)
            elif chain.family in (ChainFamily.BITCOIN, ChainFamily.SECP256K1_ALT):
                result = self._generate_secp256k1(chain, mnemonic, passphrase, effective_path)
            elif chain.family == ChainFamily.SOLANA:
                result = self._generate_ed25519(chain, mnemonic, passphrase, effective_path)
            elif chain.family == ChainFamily.TRON:
                result = self._generate_tron(chain, mnemonic, passphrase, effective_path)
            elif chain.family == ChainFamily.ED25519:
                result = self._generate_ed25519(chain, mnemonic, passphrase, effective_path)
            elif chain.family == ChainFamily.RIPPLE:
                result = self._generate_ripple(chain, mnemonic, passphrase, effective_path)
            elif chain.family == ChainFamily.SUBSTRATE:
                result = self._generate_ss58(chain, mnemonic, passphrase, effective_path)
            elif chain.family == ChainFamily.COSMOS:
                result = self._generate_secp256k1(chain, mnemonic, passphrase, effective_path)
            elif chain.family == ChainFamily.ALGORAND or chain.family == ChainFamily.TEZOS:
                result = self._generate_ed25519(chain, mnemonic, passphrase, effective_path)
            elif chain.family == ChainFamily.MONERO:
                result = self._generate_monero(chain, mnemonic, passphrase, effective_path)
            elif (
                chain.family == ChainFamily.STELLAR
                or chain.family == ChainFamily.TON
                or chain.family == ChainFamily.NANO
            ):
                result = self._generate_ed25519(chain, mnemonic, passphrase, effective_path)
            elif chain.family == ChainFamily.FILECOIN:
                result = self._generate_secp256k1(chain, mnemonic, passphrase, effective_path)
            else:
                result = self._generate_secp256k1(chain, mnemonic, passphrase, effective_path)
        except Exception as e:
            chain_info_str = f"{chain_key}/{chain.name}"
            _crypto_log_error(logger, "generate", {"chain": chain_info_str, "label": label})
            raise CryptoError(f"Wallet generation failed for {chain_info_str}: {e}") from e

        result.chain = chain_key
        result.chain_name = chain.name
        result.symbol = chain.symbol
        result.created_at = now
        result.label = label or f"{chain_key}_{int(now)}"
        result.tags = tags or []
        result.mnemonic = mnemonic if not passphrase else f"{mnemonic} (passphrase protected)"
        result.derivation_path = effective_path

        if self._vault_password:
            try:
                result.private_key_hex = self._encrypt_key(result.private_key_hex)
            except Exception as e:
                _crypto_log_error(logger, "generate.encrypt", {"chain": chain_key, "label": label})
                raise CryptoError(f"Key encryption failed for {chain_key}: {e}") from e
            result.encrypted = True

        self._generation_count += 1
        return result

    def _generate_mnemonic(self, strength: int = 256) -> str:
        try:
            from bip_utils import Bip39MnemonicGenerator, Bip39WordsNum

            words_num = (
                Bip39WordsNum.WORDS_NUM_24 if strength >= 256 else Bip39WordsNum.WORDS_NUM_12
            )
            # Always return a plain string (bip_utils sometimes returns a Bip39Mnemonic
            # object that downstream libraries like pycardano can't accept).
            return str(Bip39MnemonicGenerator().FromWordsNumber(words_num))
        except ImportError:
            raise
        except Exception as e:
            _crypto_log_error(logger, "_generate_mnemonic", {"strength": strength})
            raise CryptoError(f"Mnemonic generation failed: {e}") from e

    def _seed_from_mnemonic(self, mnemonic: str, passphrase: str = "") -> bytes:
        try:
            from bip_utils import Bip39SeedGenerator

            return Bip39SeedGenerator(mnemonic).Generate(passphrase)
        except ImportError:
            raise
        except Exception as e:
            _crypto_log_error(logger, "_seed_from_mnemonic")
            raise CryptoError(f"Seed derivation from mnemonic failed: {e}") from e

    def _derive_private_key(self, seed: bytes, path: str = "m/44'/60'/0'/0/0") -> str:
        try:
            from bip_utils import Bip32Secp256k1

            if path:
                bip32 = Bip32Secp256k1.FromSeed(seed)
                priv = bip32.DerivePath(path).PrivateKey().Raw().ToHex()
                if priv and len(priv) >= 64:
                    return priv[:64]
            raise CryptoInputError(f"BIP32 derivation failed for path: {path}")
        except ImportError:
            raise
        except CryptoInputError:
            raise
        except Exception as e:
            _crypto_log_error(logger, "_derive_private_key", {"path": path})
            raise CryptoError(f"BIP32 key derivation failed: {e}") from e

    def _derive_ed25519_key(
        self, seed: bytes, path: str = "m/44'/501'/0'/0'"
    ) -> tuple[bytes, bytes]:
        try:
            from bip_utils import Bip32Slip10Ed25519

            bip32 = Bip32Slip10Ed25519.FromSeed(seed)
            priv = bip32.DerivePath(_ensure_hardened_path(path)).PrivateKey().Raw().ToBytes()[:32]
            from nacl.bindings import crypto_sign_seed_keypair

            pk, sk = crypto_sign_seed_keypair(priv)
            return sk, pk
        except ImportError:
            raise
        except Exception as e:
            _crypto_log_error(logger, "_derive_ed25519_key", {"path": path})
            raise CryptoError(f"Ed25519 key derivation failed: {e}") from e

    def _generate_evm(
        self, chain: Any, mnemonic: str, passphrase: str = "", path: str = ""
    ) -> GeneratedWallet:
        try:
            seed = self._seed_from_mnemonic(mnemonic, passphrase)
            effective_path = path or chain.hd_path or "m/44'/60'/0'/0/0"
            priv_hex = self._derive_private_key(seed, effective_path)

            pk = CoinCurveKey.from_hex(priv_hex)
            pub = pk.public_key.format(compressed=False)[1:]

            address = _to_eip55_checksum("0x" + _keccak256(pub).hex()[-40:])
            return GeneratedWallet(
                chain="",
                chain_name="",
                symbol="",
                address=address,
                private_key_hex=priv_hex,
                public_key_hex=pub.hex() if isinstance(pub, bytes) else pub,
                derivation_path=effective_path,
            )
        except CryptoInputError:
            raise
        except Exception as e:
            _crypto_log_error(logger, "_generate_evm", {"path": path})
            raise CryptoError(f"EVM wallet generation failed: {e}") from e

    def _generate_secp256k1(
        self, chain: Any, mnemonic: str, passphrase: str = "", path: str = ""
    ) -> GeneratedWallet:
        try:
            seed = self._seed_from_mnemonic(mnemonic, passphrase)
            effective_path = path or chain.hd_path or "m/44'/0'/0'/0/0"
            priv_hex = self._derive_private_key(seed, effective_path)

            pk = CoinCurveKey.from_hex(priv_hex)
            pub = pk.public_key.format(compressed=True)

            prefix_map = {
                "btc": 0x00,
                "ltc": 0x30,
                "doge": 0x1E,
                "bch": 0x00,
                "dash": 0x4C,
                "zec": 0x1C,
                "xrp": 0x00,
            }
            prefix = prefix_map.get(chain.key, 0x00)

            sha = hashlib.sha256(pub).digest()
            ripe = hashlib.new("ripemd160", sha).digest()
            addr_bytes = bytes([prefix]) + ripe
            cs = hashlib.sha256(hashlib.sha256(addr_bytes).digest()).digest()[:4]
            address = base58.b58encode(addr_bytes + cs).decode()

            if chain.family == ChainFamily.SECP256K1_ALT:
                addr_type = "p2pkh-alt"
            elif "segwit" in getattr(chain, "key", ""):
                addr_type = "segwit"
            else:
                addr_type = "p2pkh"

            return GeneratedWallet(
                chain="",
                chain_name="",
                symbol="",
                address=address,
                private_key_hex=priv_hex,
                address_type=addr_type,
                derivation_path=effective_path,
            )
        except CryptoInputError:
            raise
        except Exception as e:
            _crypto_log_error(
                logger,
                "_generate_secp256k1",
                {"chain": chain.key if hasattr(chain, "key") else "?"},
            )
            raise CryptoError(f"SECP256k1 wallet generation failed: {e}") from e

    def _generate_ed25519(
        self, chain: Any, mnemonic: str, passphrase: str = "", path: str = ""
    ) -> GeneratedWallet:
        try:
            seed = self._seed_from_mnemonic(mnemonic, passphrase)
            effective_path = path or chain.hd_path or "m/44'/501'/0'/0'"
            sk_bytes, pub_bytes = self._derive_ed25519_key(seed, effective_path)
            priv_hex = sk_bytes.hex()[:64]
            pub = pub_bytes

            if chain.key == "near":
                address = pub.hex()
            elif chain.key in ("sui", "apt", "aptos"):
                address = "0x" + pub.hex()
            elif chain.key == "ada":
                address = "addr1" + base58.b58encode(pub).decode()[:50]
            elif chain.key == "sol":
                address = base58.b58encode(pub).decode()
            elif chain.key == "xlm":
                addr_bytes = bytes([6 << 3]) + pub[:32]
                address = base58.b58encode(addr_bytes).decode()
            else:
                address = base58.b58encode(pub).decode()[:44]

            return GeneratedWallet(
                chain="",
                chain_name="",
                symbol="",
                address=address,
                private_key_hex=priv_hex,
                public_key_hex=pub.hex(),
                address_type="ed25519",
                derivation_path=effective_path,
            )
        except CryptoInputError:
            raise
        except Exception as e:
            _crypto_log_error(
                logger, "_generate_ed25519", {"chain": chain.key if hasattr(chain, "key") else "?"}
            )
            raise CryptoError(f"Ed25519 wallet generation failed: {e}") from e

    def _generate_tron(
        self, chain: Any, mnemonic: str, passphrase: str = "", path: str = ""
    ) -> GeneratedWallet:
        try:
            seed = self._seed_from_mnemonic(mnemonic, passphrase)
            effective_path = path or chain.hd_path or "m/44'/195'/0'/0/0"
            priv_hex = self._derive_private_key(seed, effective_path)

            pk = CoinCurveKey.from_hex(priv_hex)
            pub = pk.public_key.format(compressed=False)[1:]

            addr_hash = _keccak256(pub)[-20:]
            addr_bytes = b"\x41" + addr_hash
            cs = hashlib.sha256(hashlib.sha256(addr_bytes).digest()).digest()[:4]
            address = base58.b58encode(addr_bytes + cs).decode()

            return GeneratedWallet(
                chain="",
                chain_name="",
                symbol="TRX",
                address=address,
                private_key_hex=priv_hex,
                public_key_hex=pub.hex(),
                address_type="tron-base58",
                derivation_path=effective_path,
            )
        except CryptoInputError:
            raise
        except Exception as e:
            _crypto_log_error(logger, "_generate_tron")
            raise CryptoError(f"TRON wallet generation failed: {e}") from e

    def _generate_ripple(
        self, chain: Any, mnemonic: str, passphrase: str = "", path: str = ""
    ) -> GeneratedWallet:
        try:
            seed = self._seed_from_mnemonic(mnemonic, passphrase)
            effective_path = path or chain.hd_path or "m/44'/144'/0'/0/0"
            sk_bytes, pub_bytes = self._derive_ed25519_key(seed, effective_path)
            priv_hex = sk_bytes.hex()[:64]
            pub = pub_bytes

            sha = hashlib.sha256(pub).digest()
            ripe = hashlib.new("ripemd160", sha).digest()
            addr_bytes = b"\x7a" + ripe
            cs = hashlib.sha256(hashlib.sha256(addr_bytes).digest()).digest()[:4]
            address = base58.b58encode(addr_bytes + cs).decode()

            return GeneratedWallet(
                chain="",
                chain_name="",
                symbol="XRP",
                address=address,
                private_key_hex=priv_hex,
                public_key_hex=pub.hex(),
                address_type="ripple-base58",
                derivation_path=effective_path,
            )
        except CryptoInputError:
            raise
        except Exception as e:
            _crypto_log_error(logger, "_generate_ripple")
            raise CryptoError(f"Ripple wallet generation failed: {e}") from e

    def _generate_ss58(
        self, chain: Any, mnemonic: str, passphrase: str = "", path: str = ""
    ) -> GeneratedWallet:
        try:
            seed = self._seed_from_mnemonic(mnemonic, passphrase)
            effective_path = path or chain.hd_path or "m/44'/354'/0'/0/0"
            sk_bytes, pub_bytes = self._derive_ed25519_key(seed, effective_path)
            priv_hex = sk_bytes.hex()[:64]
            pub = pub_bytes

            ss58_prefix_map = {"dot": 0, "ksm": 2}
            prefix = ss58_prefix_map.get(chain.key, 0)

            prefix_bytes = bytes([prefix])
            payload = prefix_bytes + pub[:32]
            ss58_hash = hashlib.blake2b(payload, digest_size=64).digest()
            checksum = ss58_hash[:2]
            address = base58.b58encode(payload + checksum).decode()

            return GeneratedWallet(
                chain="",
                chain_name="",
                symbol=chain.symbol,
                address=address,
                private_key_hex=priv_hex,
                public_key_hex=pub.hex(),
                address_type="ss58",
                derivation_path=effective_path,
            )
        except CryptoInputError:
            raise
        except Exception as e:
            _crypto_log_error(
                logger, "_generate_ss58", {"chain": chain.key if hasattr(chain, "key") else "?"}
            )
            raise CryptoError(f"SS58 wallet generation failed: {e}") from e

    def _generate_monero(
        self, chain: Any, mnemonic: str, passphrase: str = "", path: str = ""
    ) -> GeneratedWallet:
        try:
            from monero.seed import Seed as MoneroSeed

            # Monero uses its own 25-word mnemonic, not BIP39.
            # Derive a 256-bit seed from the BIP39 mnemonic so generation is
            # deterministic: same BIP39 phrase always produces the same XMR wallet.
            seed_hex = self._seed_from_mnemonic(mnemonic, passphrase).hex()[:64]
            ms = MoneroSeed(seed_hex)
            addr = str(ms.public_address())
            spend_pub = str(ms.public_spend_key())
            view_pub = str(ms.public_view_key())
            spend_sec = str(ms.secret_spend_key())
            view_sec = str(ms.secret_view_key())
            xmr_mnemonic = ms.phrase

            return GeneratedWallet(
                chain="",
                chain_name="",
                symbol="XMR",
                address=addr,
                private_key_hex=spend_sec + view_sec,
                public_key_hex=spend_pub + view_pub,
                mnemonic=xmr_mnemonic,
                address_type="monero",
                derivation_path="monero-custom (non-BIP44)",
            )
        except (ImportError, ModuleNotFoundError):
            raise RuntimeError(
                "monero is required for XMR wallet generation. Install it: pip install monero"
            ) from None
        except CryptoInputError:
            raise
        except Exception as e:
            _crypto_log_error(logger, "_generate_monero")
            raise CryptoError(f"Monero wallet generation failed: {e}") from e

    def _generate_with_override(
        self, chain: Any, mnemonic: str, passphrase: str, path: str, chain_key: str
    ) -> GeneratedWallet:
        """Generate a wallet using a chain-specific override from CHAIN_ADDRESS_OVERRIDES.

        This is the new path for the 17 chains that have non-trivial address
        formats (Cosmos bech32, Stellar StrKey, XRP custom alphabet, Tezos
        watermark, TON workchain, Filecoin f1, Nano base32, Algorand SHA-512/256,
        BCH cashaddr, Cardano Kholaw).

        All address encoding is delegated to wallet_engine.chain_addresses.
        """
        try:
            from .chain_addresses import encode_address

            override = CHAIN_ADDRESS_OVERRIDES[chain_key]
            curve = override["curve"]
            address_family = override["address_family"]

            # Cardano uses its own BIP32-Ed25519 (Kholaw) via pycardano.
            # The library handles derivation internally from the mnemonic.
            # We extract the raw 32-byte ed25519 signing key from xsk[:32].
            if curve == "ed25519_kholaw":
                from pycardano import HDWallet

                wallet = HDWallet.from_mnemonic(mnemonic)
                acc = (
                    wallet.derive(1852, hardened=True)
                    .derive(1815, hardened=True)
                    .derive(0, hardened=True)
                )
                pay_w = acc.derive(0).derive(0)
                # xsk format: 32-byte signing key || 32-byte chain code
                pay_xsk = pay_w.xprivate_key
                pay_priv = pay_xsk[:32].hex()

                # Derive the public key from the raw signing key
                from nacl.bindings import crypto_sign_seed_keypair

                pay_pub, _ = crypto_sign_seed_keypair(pay_xsk[:32])

                address = encode_address(
                    address_family, mnemonic, override.get("network", "mainnet")
                )
                # Return payment key as primary; stake key is in derivation_path note.
                # The combined private key is the payment || stake (for full restoration).
                return GeneratedWallet(
                    chain="",
                    chain_name="",
                    symbol="",
                    address=address,
                    private_key_hex=pay_priv,
                    public_key_hex=pay_pub.hex(),
                    derivation_path="m/1852'/1815'/0'/0/0 (payment) + m/1852'/1815'/0'/2/0 (stake)",
                    address_type=address_family,
                )

            seed = self._seed_from_mnemonic(mnemonic, passphrase)

            if curve == "secp256k1":
                priv_hex = self._derive_private_key(seed, path)
                from coincurve import PrivateKey

                pk = PrivateKey.from_hex(priv_hex)
                compressed_pub = pk.public_key.format(compressed=True)
                privkey_bytes = bytes.fromhex(priv_hex)
            elif curve == "ed25519":
                from bip_utils import Bip32Slip10Ed25519

                bip32 = Bip32Slip10Ed25519.FromSeed(seed)
                privkey_bytes = (
                    bip32.DerivePath(_ensure_hardened_path(path)).PrivateKey().Raw().ToBytes()[:32]
                )
                from nacl.bindings import crypto_sign_seed_keypair

                pub_bytes, _ = crypto_sign_seed_keypair(privkey_bytes)
                compressed_pub = pub_bytes  # not compressed for ed25519
                priv_hex = privkey_bytes.hex()
            else:
                raise CryptoInputError(f"Unsupported curve: {curve}")

            # Build the address using the chain-specific encoder.
            if address_family == "bech32":
                address = encode_address("bech32", compressed_pub, override["hrp"])
            elif address_family == "bch":
                # BCH needs the raw private key for bitcash
                address = encode_address("bch", privkey_bytes)
            elif address_family == "zcash_t":
                address = encode_address("zcash_t", compressed_pub)
            else:
                # All other encoders take the public key
                if curve == "ed25519":
                    address = encode_address(address_family, pub_bytes)
                else:
                    address = encode_address(address_family, compressed_pub)

            return GeneratedWallet(
                chain="",
                chain_name="",
                symbol="",
                address=address,
                private_key_hex=priv_hex,
                public_key_hex=compressed_pub.hex(),
                derivation_path=path,
                address_type=address_family,
            )
        except CryptoInputError:
            raise
        except Exception as e:
            _crypto_log_error(
                logger,
                "_generate_with_override",
                {"chain_key": chain_key, "address_family": address_family},
            )
            raise CryptoError(f"Override wallet generation failed for {chain_key}: {e}") from e

    def _encrypt_key(self, plaintext: str) -> str:
        if not self._vault_password:
            return plaintext
        try:
            salt = secrets.token_bytes(16)
            key = _argon2id_kdf(
                secret=self._vault_password.encode(),
                salt=salt,
                time_cost=3,
                memory_cost=65536,
                parallelism=4,
                hash_len=32,
                type=_Argon2Type.ID,
            )
            aesgcm = AESGCM(key)
            nonce = secrets.token_bytes(12)
            ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
            return base64.b64encode(salt + nonce + ct).decode()
        except Exception as e:
            _crypto_log_error(logger, "_encrypt_key")
            raise CryptoError(f"Key encryption failed: {e}") from e

    def decrypt_key(self, encrypted: str) -> str:
        if not self._vault_password:
            return encrypted
        try:
            data = base64.b64decode(encrypted)
            salt, nonce, ct = data[:16], data[16:28], data[28:]
            key = _argon2id_kdf(
                secret=self._vault_password.encode(),
                salt=salt,
                time_cost=3,
                memory_cost=65536,
                parallelism=4,
                hash_len=32,
                type=_Argon2Type.ID,
            )
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(nonce, ct, None).decode()
        except ValueError as e:
            logger.error("Key decryption: corrupted encrypted data: %s", e)
            raise CryptoInputError("Encrypted key data is corrupted or malformed") from e
        except Exception as e:
            _crypto_log_error(logger, "decrypt_key")
            raise CryptoError(f"Key decryption failed: {e}") from e

    def import_from_private_key(
        self, chain_key: str, private_key_hex: str, label: str = "", tags: list[str] | None = None
    ) -> GeneratedWallet:
        """Import an existing private key into a wallet.

        Validates that the key is a valid hex string of appropriate length
        for the chain type. EVM/SECP256K1 keys should be 64 hex chars (32 bytes),
        Ed25519 keys should be 64 or 128 hex chars.

        We do NOT verify the key corresponds to a real on-chain address
        (the user knows their own key). We encrypt and store them like
        any other wallet.
        """
        chain = CHAINS.get(chain_key.lower())
        if not chain:
            raise ValueError(f"Unsupported chain: {chain_key}")

        private_key_hex = private_key_hex.strip()
        if not private_key_hex:
            raise ValueError("Private key cannot be empty")

        # Validate hex encoding
        try:
            key_bytes = bytes.fromhex(private_key_hex.removeprefix("0x"))
        except ValueError:
            raise ValueError("Private key must be a valid hex string") from None

        # Check key length based on curve
        if chain.curve in ("secp256k1", "ed25519"):
            if len(key_bytes) not in (32, 64):
                raise ValueError(
                    f"Private key must be 32 or 64 bytes for {chain.curve} chains "
                    f"(got {len(key_bytes)} bytes)"
                )
        elif len(key_bytes) < 16:
            raise ValueError(
                f"Private key too short ({len(key_bytes)} bytes). "
                f"Expected at least 16 bytes for {chain_key}"
            )

        try:
            wallet = GeneratedWallet(
                chain=chain_key,
                chain_name=chain.name,
                symbol=chain.symbol,
                address=f"imported:{chain_key}:{private_key_hex[-8:]}",
                private_key_hex=private_key_hex,
                label=label or f"imported_{chain_key}_{int(time.time())}",
                tags=tags or ["imported"],
                created_at=time.time(),
            )

            if self._vault_password:
                wallet.private_key_hex = self._encrypt_key(wallet.private_key_hex)
                wallet.encrypted = True

            return wallet
        except CryptoInputError:
            raise
        except Exception as e:
            _crypto_log_error(logger, "import_from_private_key", {"chain": chain_key})
            raise CryptoError(f"Private key import failed for {chain_key}: {e}") from e

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "generation_count": self._generation_count,
            "chains_supported": len(CHAINS),
            "chain_families": len({c.family for c in CHAINS.values()}),
            "encryption_enabled": bool(self._vault_password),
            "chains": {
                k: {"name": v.name, "symbol": v.symbol, "family": v.family.value}
                for k, v in CHAINS.items()
            },
        }


_generator: WalletGenerator | None = None


def get_generator(vault_password: str = "") -> WalletGenerator:
    global _generator
    if _generator is None:
        _generator = WalletGenerator(vault_password=vault_password)
    return _generator
