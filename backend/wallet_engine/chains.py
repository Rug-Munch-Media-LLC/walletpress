"""Multi-chain registry — 55 chains, all metadata, all derivation paths.

This is the single source of truth for chain support across the entire
WalletPress platform. Every chain has known-good BIP44 derivation paths,
address validation patterns, and RPC endpoints.

Trust principle: All derivation follows BIP39/BIP32/BIP44/BIP49/BIP84
standards. Users can verify WalletPress addresses match any standard wallet
software. Every chain's test vectors are documented and tested.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger("wp.chains")


class ChainFamily(Enum):
    BITCOIN = "bitcoin"
    EVM = "evm"
    SOLANA = "solana"
    TRON = "tron"
    ED25519 = "ed25519"
    SECP256K1_ALT = "secp256k1_alt"
    RIPPLE = "ripple"
    SUBSTRATE = "substrate"
    COSMOS = "cosmos"
    ALGORAND = "algorand"
    TEZOS = "tezos"
    MONERO = "monero"
    STELLAR = "stellar"
    TON = "ton"
    NANO = "nano"
    CASPER = "casper"
    ELROND = "elrond"
    HEDERA = "hedera"
    INTERNET_COMPUTER = "internet_computer"
    FILECOIN = "filecoin"
    ZILLIQA = "zilliqa"


@dataclass
class ChainInfo:
    key: str
    name: str
    family: ChainFamily
    symbol: str
    decimals: int = 18
    slip44: int = 0
    hd_path: str = ""
    testnet_hd_path: str = ""
    address_pattern: str = ""
    address_length: int = 0
    explorer_url: str = ""
    testnet_explorer: str = ""
    rpc_url: str = ""
    description: str = ""
    icon: str = ""
    is_testnet: bool = False
    requires_bip39: bool = True
    curve: str = "secp256k1"
    native_token: str = ""


CHAINS: dict[str, ChainInfo] = {
    # ── Bitcoin Family ──────────────────────────────────────
    "btc": ChainInfo(
        key="btc", name="Bitcoin", family=ChainFamily.BITCOIN, symbol="BTC",
        slip44=0, hd_path="m/44'/0'/0'/0/0", decimals=8,
        address_pattern="^(1|3|bc1)[a-zA-Z0-9]{25,62}$",
        explorer_url="https://blockstream.info",
        curve="secp256k1", native_token="BTC",
        description="Bitcoin — the original cryptocurrency",
    ),
    "btc-segwit": ChainInfo(
        key="btc-segwit", name="Bitcoin SegWit", family=ChainFamily.BITCOIN, symbol="BTC",
        slip44=0, hd_path="m/49'/0'/0'/0/0", decimals=8,
        address_pattern="^(3|bc1)[a-zA-Z0-9]{25,62}$",
        explorer_url="https://blockstream.info",
        curve="secp256k1", native_token="BTC",
        description="Bitcoin SegWit (P2SH-P2WPKH) — lower fees",
    ),
    "btc-native-segwit": ChainInfo(
        key="btc-native-segwit", name="Bitcoin Native SegWit", family=ChainFamily.BITCOIN, symbol="BTC",
        slip44=0, hd_path="m/84'/0'/0'/0/0", decimals=8,
        address_pattern="^bc1[a-zA-Z0-9]{39,59}$",
        explorer_url="https://blockstream.info",
        curve="secp256k1", native_token="BTC",
        description="Bitcoin Native SegWit (P2WPKH) — lowest fees",
    ),
    # ── EVM Family ──────────────────────────────────────────
    "eth": ChainInfo(
        key="eth", name="Ethereum", family=ChainFamily.EVM, symbol="ETH",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://etherscan.io",
        rpc_url="https://eth.llamarpc.com", native_token="ETH",
        description="Ethereum — smart contract platform",
    ),
    "base": ChainInfo(
        key="base", name="Base", family=ChainFamily.EVM, symbol="ETH",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://basescan.org",
        rpc_url="https://mainnet.base.org", native_token="ETH",
        description="Coinbase Base L2",
    ),
    "polygon": ChainInfo(
        key="polygon", name="Polygon", family=ChainFamily.EVM, symbol="POL",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://polygonscan.com",
        rpc_url="https://polygon-rpc.com", native_token="POL",
        description="Polygon PoS",
    ),
    "arbitrum": ChainInfo(
        key="arbitrum", name="Arbitrum One", family=ChainFamily.EVM, symbol="ETH",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://arbiscan.io",
        rpc_url="https://arb1.arbitrum.io/rpc", native_token="ETH",
        description="Arbitrum One L2",
    ),
    "optimism": ChainInfo(
        key="optimism", name="Optimism", family=ChainFamily.EVM, symbol="ETH",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://optimistic.etherscan.io",
        rpc_url="https://mainnet.optimism.io", native_token="ETH",
        description="Optimism L2",
    ),
    "avalanche": ChainInfo(
        key="avalanche", name="Avalanche C-Chain", family=ChainFamily.EVM, symbol="AVAX",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://snowtrace.io",
        rpc_url="https://api.avax.network/ext/bc/C/rpc", native_token="AVAX",
        description="Avalanche C-Chain",
    ),
    "bsc": ChainInfo(
        key="bsc", name="BNB Smart Chain", family=ChainFamily.EVM, symbol="BNB",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://bscscan.com",
        rpc_url="https://bsc-dataseed.binance.org", native_token="BNB",
        description="BNB Smart Chain",
    ),
    "fantom": ChainInfo(
        key="fantom", name="Fantom", family=ChainFamily.EVM, symbol="FTM",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://ftmscan.com",
        rpc_url="https://rpc.ftm.tools", native_token="FTM",
        description="Fantom Opera",
    ),
    "gnosis": ChainInfo(
        key="gnosis", name="Gnosis Chain", family=ChainFamily.EVM, symbol="XDAI",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://gnosisscan.io",
        rpc_url="https://rpc.gnosischain.com", native_token="XDAI",
        description="Gnosis Chain (formerly xDai)",
    ),
    "celo": ChainInfo(
        key="celo", name="Celo", family=ChainFamily.EVM, symbol="CELO",
        slip44=52752, hd_path="m/44'/52752'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://celoscan.io",
        rpc_url="https://forno.celo.org", native_token="CELO",
        description="Celo — mobile-first DeFi",
    ),
    "scroll": ChainInfo(
        key="scroll", name="Scroll", family=ChainFamily.EVM, symbol="ETH",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://scrollscan.com",
        rpc_url="https://rpc.scroll.io", native_token="ETH",
        description="Scroll zkEVM L2",
    ),
    "zksync": ChainInfo(
        key="zksync", name="zkSync Era", family=ChainFamily.EVM, symbol="ETH",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://explorer.zksync.io",
        rpc_url="https://mainnet.era.zksync.io", native_token="ETH",
        description="zkSync Era zkEVM L2",
    ),
    "blast": ChainInfo(
        key="blast", name="Blast", family=ChainFamily.EVM, symbol="ETH",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://blastscan.io",
        rpc_url="https://rpc.blast.io", native_token="ETH",
        description="Blast L2",
    ),
    "mantle": ChainInfo(
        key="mantle", name="Mantle", family=ChainFamily.EVM, symbol="MNT",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://explorer.mantle.xyz",
        rpc_url="https://rpc.mantle.xyz", native_token="MNT",
        description="Mantle L2",
    ),
    "linea": ChainInfo(
        key="linea", name="Linea", family=ChainFamily.EVM, symbol="ETH",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://lineascan.build",
        rpc_url="https://rpc.linea.build", native_token="ETH",
        description="Linea zkEVM by ConsenSys",
    ),
    "metis": ChainInfo(
        key="metis", name="Metis", family=ChainFamily.EVM, symbol="METIS",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://andromeda-explorer.metis.io",
        rpc_url="https://andromeda.metis.io", native_token="METIS",
        description="Metis L2",
    ),
    # ── Solana ───────────────────────────────────────────────
    "sol": ChainInfo(
        key="sol", name="Solana", family=ChainFamily.SOLANA, symbol="SOL",
        slip44=501, hd_path="m/44'/501'/0'/0'", decimals=9,
        address_pattern="^[1-9A-HJ-NP-Za-km-z]{32,44}$",
        explorer_url="https://solscan.io",
        rpc_url="https://api.mainnet-beta.solana.com", native_token="SOL",
        curve="ed25519",
        description="Solana — high-performance blockchain",
    ),
    # ── TRON ─────────────────────────────────────────────────
    "trx": ChainInfo(
        key="trx", name="TRON", family=ChainFamily.TRON, symbol="TRX",
        slip44=195, hd_path="m/44'/195'/0'/0/0", decimals=6,
        address_pattern="^T[a-zA-Z0-9]{33}$",
        explorer_url="https://tronscan.org",
        rpc_url="https://api.trongrid.io", native_token="TRX",
        description="TRON network",
    ),
    # ── Alt L1s (secp256k1) ──────────────────────────────────
    "doge": ChainInfo(
        key="doge", name="Dogecoin", family=ChainFamily.SECP256K1_ALT, symbol="DOGE",
        slip44=3, hd_path="m/44'/3'/0'/0/0", decimals=8,
        address_pattern="^D[a-zA-Z0-9]{33}$",
        explorer_url="https://dogechain.info",
        curve="secp256k1", native_token="DOGE",
        description="Dogecoin — much wow",
    ),
    "ltc": ChainInfo(
        key="ltc", name="Litecoin", family=ChainFamily.SECP256K1_ALT, symbol="LTC",
        slip44=2, hd_path="m/44'/2'/0'/0/0", decimals=8,
        address_pattern="^(L|M|ltc1)[a-zA-Z0-9]{25,62}$",
        explorer_url="https://blockchair.com/litecoin",
        curve="secp256k1", native_token="LTC",
        description="Litecoin — silver to Bitcoin's gold",
    ),
    "bch": ChainInfo(
        key="bch", name="Bitcoin Cash", family=ChainFamily.SECP256K1_ALT, symbol="BCH",
        slip44=145, hd_path="m/44'/145'/0'/0/0", decimals=8,
        address_pattern="^(bitcoincash:|q|p)[a-zA-Z0-9]{25,62}$",
        explorer_url="https://blockchair.com/bitcoin-cash",
        curve="secp256k1", native_token="BCH",
        description="Bitcoin Cash",
    ),
    "dash": ChainInfo(
        key="dash", name="Dash", family=ChainFamily.SECP256K1_ALT, symbol="DASH",
        slip44=5, hd_path="m/44'/5'/0'/0/0", decimals=8,
        address_pattern="^X[a-zA-Z0-9]{33}$",
        explorer_url="https://blockchair.com/dash",
        curve="secp256k1", native_token="DASH",
        description="Dash — digital cash",
    ),
    "zec": ChainInfo(
        key="zec", name="Zcash", family=ChainFamily.SECP256K1_ALT, symbol="ZEC",
        slip44=133, hd_path="m/44'/133'/0'/0/0", decimals=8,
        address_pattern="^(t1|t3|zs1)[a-zA-Z0-9]{25,90}$",
        explorer_url="https://blockchair.com/zcash",
        curve="secp256k1", native_token="ZEC",
        description="Zcash — privacy-focused",
    ),
    # ── Ed25519 Family ───────────────────────────────────────
    "ada": ChainInfo(
        key="ada", name="Cardano", family=ChainFamily.ED25519, symbol="ADA",
        slip44=1815, hd_path="m/1852'/1815'/0'/0/0", decimals=6,
        address_pattern="^addr1[a-zA-Z0-9]{50,}$",
        explorer_url="https://cardanoscan.io",
        curve="ed25519", native_token="ADA",
        description="Cardano Shelley",
    ),
    "near": ChainInfo(
        key="near", name="NEAR Protocol", family=ChainFamily.ED25519, symbol="NEAR",
        slip44=397, hd_path="m/44'/397'/0'/0'", decimals=24,
        address_pattern="^[a-f0-9]{64}$",
        explorer_url="https://nearblocks.io",
        curve="ed25519", native_token="NEAR",
        description="NEAR Protocol",
    ),
    "sui": ChainInfo(
        key="sui", name="Sui", family=ChainFamily.ED25519, symbol="SUI",
        slip44=784, hd_path="m/44'/784'/0'/0'", decimals=9,
        address_pattern="^0x[a-fA-F0-9]{64}$",
        explorer_url="https://suiscan.xyz",
        curve="ed25519", native_token="SUI",
        description="Sui Network",
    ),
    "aptos": ChainInfo(
        key="apt", name="Aptos", family=ChainFamily.ED25519, symbol="APT",
        slip44=637, hd_path="m/44'/637'/0'/0'", decimals=8,
        address_pattern="^0x[a-fA-F0-9]{64}$",
        explorer_url="https://aptoscan.com",
        curve="ed25519", native_token="APT",
        description="Aptos",
    ),
    # ── Ripple ───────────────────────────────────────────────
    "xrp": ChainInfo(
        key="xrp", name="Ripple XRP", family=ChainFamily.RIPPLE, symbol="XRP",
        slip44=144, hd_path="m/44'/144'/0'/0/0", decimals=6,
        address_pattern="^r[a-zA-Z0-9]{24,34}$",
        explorer_url="https://xrpscan.com",
        curve="secp256k1", native_token="XRP",
        description="Ripple XRP Ledger",
    ),
    # ── Substrate ────────────────────────────────────────────
    "dot": ChainInfo(
        key="dot", name="Polkadot", family=ChainFamily.SUBSTRATE, symbol="DOT",
        slip44=354, hd_path="m/44'/354'/0'/0/0", decimals=10,
        address_pattern="^1[a-zA-Z0-9]{47}$",
        explorer_url="https://polkadot.subscan.io",
        curve="sr25519", native_token="DOT",
        description="Polkadot — sharded multichain",
    ),
    "ksm": ChainInfo(
        key="ksm", name="Kusama", family=ChainFamily.SUBSTRATE, symbol="KSM",
        slip44=434, hd_path="m/44'/434'/0'/0/0", decimals=12,
        address_pattern="^[a-km-zA-HJ-NP-Z1-9]{47}$",
        explorer_url="https://kusama.subscan.io",
        curve="sr25519", native_token="KSM",
        description="Kusama — Polkadot's canary network",
    ),
    # ── Cosmos ───────────────────────────────────────────────
    "atom": ChainInfo(
        key="atom", name="Cosmos Hub", family=ChainFamily.COSMOS, symbol="ATOM",
        slip44=118, hd_path="m/44'/118'/0'/0/0", decimals=6,
        address_pattern="^cosmos1[a-zA-Z0-9]{38}$",
        explorer_url="https://mintscan.io/cosmos",
        curve="secp256k1", native_token="ATOM",
        description="Cosmos Hub",
    ),
    "osmo": ChainInfo(
        key="osmo", name="Osmosis", family=ChainFamily.COSMOS, symbol="OSMO",
        slip44=118, hd_path="m/44'/118'/0'/0/0", decimals=6,
        address_pattern="^osmo1[a-zA-Z0-9]{38}$",
        explorer_url="https://mintscan.io/osmosis",
        curve="secp256k1", native_token="OSMO",
        description="Osmosis DEX",
    ),
    "inj": ChainInfo(
        key="inj", name="Injective", family=ChainFamily.COSMOS, symbol="INJ",
        slip44=60, hd_path="m/44'/60'/0'/0/0", decimals=18,
        address_pattern="^inj1[a-zA-Z0-9]{38}$",
        explorer_url="https://explorer.injective.network",
        curve="secp256k1", native_token="INJ",
        description="Injective — DeFi derivatives",
    ),
    "juno": ChainInfo(
        key="juno", name="Juno", family=ChainFamily.COSMOS, symbol="JUNO",
        slip44=118, hd_path="m/44'/118'/0'/0/0", decimals=6,
        address_pattern="^juno1[a-zA-Z0-9]{38}$",
        explorer_url="https://mintscan.io/juno",
        curve="secp256k1", native_token="JUNO",
        description="Juno — smart contract hub",
    ),
    "sei": ChainInfo(
        key="sei", name="Sei", family=ChainFamily.COSMOS, symbol="SEI",
        slip44=118, hd_path="m/44'/118'/0'/0/0", decimals=6,
        address_pattern="^sei1[a-zA-Z0-9]{38}$",
        explorer_url="https://seiscan.app",
        curve="secp256k1", native_token="SEI",
        description="Sei — fastest L1",
    ),
    # ── Algorand ─────────────────────────────────────────────
    "algo": ChainInfo(
        key="algo", name="Algorand", family=ChainFamily.ALGORAND, symbol="ALGO",
        slip44=283, hd_path="m/44'/283'/0'/0'", decimals=6,
        address_pattern="^[A-Z0-9]{58}$",
        explorer_url="https://algoexplorer.io",
        curve="ed25519", native_token="ALGO",
        description="Algorand — pure proof-of-stake",
    ),
    # ── Tezos ────────────────────────────────────────────────
    "xtz": ChainInfo(
        key="xtz", name="Tezos", family=ChainFamily.TEZOS, symbol="XTZ",
        slip44=1729, hd_path="m/44'/1729'/0'/0'", decimals=6,
        address_pattern="^(tz1|tz2|tz3)[a-zA-Z0-9]{33}$",
        explorer_url="https://tzkt.io",
        curve="ed25519", native_token="XTZ",
        description="Tezos — self-amending L1",
    ),
    # ── Monero ───────────────────────────────────────────────
    "xmr": ChainInfo(
        key="xmr", name="Monero", family=ChainFamily.MONERO, symbol="XMR",
        slip44=128, hd_path="m/44'/128'/0'/0/0", decimals=12,
        address_pattern="^[48][a-zA-Z0-9]{94}$",
        explorer_url="https://xmrchain.net",
        curve="ed25519", native_token="XMR",
        description="Monero — private, untraceable",
    ),
    # ── Stellar ──────────────────────────────────────────────
    "xlm": ChainInfo(
        key="xlm", name="Stellar", family=ChainFamily.STELLAR, symbol="XLM",
        slip44=148, hd_path="m/44'/148'/0'/0'", decimals=7,
        address_pattern="^G[A-Z0-9]{55}$",
        explorer_url="https://stellar.expert",
        curve="ed25519", native_token="XLM",
        description="Stellar — cross-border payments",
    ),
    # ── TON ──────────────────────────────────────────────────
    "ton": ChainInfo(
        key="ton", name="TON", family=ChainFamily.TON, symbol="TON",
        slip44=396, hd_path="m/44'/396'/0'/0'", decimals=9,
        address_pattern="^[EQ][a-fA-F0-9]{48}$",
        explorer_url="https://tonscan.org",
        curve="ed25519", native_token="TON",
        description="The Open Network",
    ),
    # ── Nano ─────────────────────────────────────────────────
    "nano": ChainInfo(
        key="nano", name="Nano", family=ChainFamily.NANO, symbol="XNO",
        slip44=165, hd_path="m/44'/165'/0'", decimals=30,
        address_pattern="^nano_[1-9a-z]{60}$",
        explorer_url="https://nanolooker.com",
        curve="ed25519", native_token="XNO",
        description="Nano — feeless, instant",
    ),
    # ── Filecoin ─────────────────────────────────────────────
    "fil": ChainInfo(
        key="fil", name="Filecoin", family=ChainFamily.FILECOIN, symbol="FIL",
        slip44=461, hd_path="m/44'/461'/0'/0/0", decimals=18,
        address_pattern="^f1[a-zA-Z0-9]{40}$",
        explorer_url="https://filfox.info",
        curve="secp256k1", native_token="FIL",
        description="Filecoin — decentralized storage",
    ),
    # ── Additional EVM chains ────────────────────────────────
    "opbnb": ChainInfo(
        key="opbnb", name="opBNB", family=ChainFamily.EVM, symbol="BNB",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://opbnbscan.com",
        rpc_url="https://opbnb-mainnet-rpc.bnbchain.org", native_token="BNB",
        description="opBNB L2",
    ),
    "core": ChainInfo(
        key="core", name="Core Chain", family=ChainFamily.EVM, symbol="CORE",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://scan.coredao.org",
        rpc_url="https://rpc.coredao.org", native_token="CORE",
        description="Core Chain — Bitcoin-powered EVM",
    ),
    "frax": ChainInfo(
        key="frax", name="Fraxchain", family=ChainFamily.EVM, symbol="FXS",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://fraxscan.com",
        rpc_url="https://rpc.frax.com", native_token="FXS",
        description="Fraxchain L2",
    ),
    "kava": ChainInfo(
        key="kava", name="Kava EVM", family=ChainFamily.EVM, symbol="KAVA",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://kavascan.com",
        rpc_url="https://evm.kava.io", native_token="KAVA",
        description="Kava EVM co-chain",
    ),
    "moonbeam": ChainInfo(
        key="moonbeam", name="Moonbeam", family=ChainFamily.EVM, symbol="GLMR",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://moonscan.io",
        rpc_url="https://rpc.api.moonbeam.network", native_token="GLMR",
        description="Moonbeam — Polkadot parachain EVM",
    ),
    "cronos": ChainInfo(
        key="cronos", name="Cronos", family=ChainFamily.EVM, symbol="CRO",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://cronoscan.com",
        rpc_url="https://evm.cronos.org", native_token="CRO",
        description="Cronos — Crypto.org EVM",
    ),
    "aurora": ChainInfo(
        key="aurora", name="Aurora", family=ChainFamily.EVM, symbol="ETH",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://aurorascan.dev",
        rpc_url="https://mainnet.aurora.dev", native_token="ETH",
        description="Aurora — NEAR EVM",
    ),
    "harmony": ChainInfo(
        key="harmony", name="Harmony", family=ChainFamily.EVM, symbol="ONE",
        slip44=1023, hd_path="m/44'/1023'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://explorer.harmony.one",
        rpc_url="https://api.harmony.one", native_token="ONE",
        description="Harmony — sharded L1",
    ),
    "boba": ChainInfo(
        key="boba", name="Boba Network", family=ChainFamily.EVM, symbol="BOBA",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://bobascan.com",
        rpc_url="https://mainnet.boba.network", native_token="ETH",
        description="Boba Network L2",
    ),
    "evmos": ChainInfo(
        key="evmos", name="Evmos", family=ChainFamily.EVM, symbol="EVMOS",
        slip44=60, hd_path="m/44'/60'/0'/0/0",
        address_pattern="^0x[a-fA-F0-9]{40}$",
        explorer_url="https://evmos.org",
        rpc_url="https://evmos.lava.build", native_token="EVMOS",
        description="Evmos — EVM on Cosmos",
    ),
}

# ── Chain Groups ──────────────────────────────────────────────────

CHAIN_GROUPS: dict[str, list[str]] = {
    "evm": [k for k, v in CHAINS.items() if v.family == ChainFamily.EVM],
    "bitcoin": [k for k, v in CHAINS.items() if v.family in (ChainFamily.BITCOIN, ChainFamily.SECP256K1_ALT)],
    "solana": ["sol"],
    "cosmos": [k for k, v in CHAINS.items() if v.family == ChainFamily.COSMOS],
    "substrate": [k for k, v in CHAINS.items() if v.family == ChainFamily.SUBSTRATE],
    "ed25519": [k for k, v in CHAINS.items() if v.curve == "ed25519"],
    "privacy": ["xmr", "zec"],
    "l1": [k for k, v in CHAINS.items() if v.family in (
        ChainFamily.SOLANA, ChainFamily.TRON, ChainFamily.ALGORAND,
        ChainFamily.TEZOS, ChainFamily.RIPPLE, ChainFamily.NANO,
        ChainFamily.TON, ChainFamily.STELLAR,
    )],
    "l2": [k for k, v in CHAINS.items() if v.family == ChainFamily.EVM and v.key not in ("eth", "bsc", "avalanche", "polygon", "fantom", "gnosis", "celo", "harmony")],
    "all": list(CHAINS.keys()),
}

# ── Tiers ─────────────────────────────────────────────────────────

TIERS = {
    "free": {
        "label": "Free",
        "chains": ["btc", "eth", "sol"],
        "max_wallets": 10,
        "features": ["basic_generation", "wp_plugin"],
    },
    "starter": {
        "label": "Starter",
        "price_usd": 49,
        "chains": list(CHAINS.keys())[:12],
        "max_wallets": 500,
        "features": ["basic_generation", "batch_generation", "vault", "mnemonic_convert", "wp_plugin", "cli", "export"],
    },
    "pro": {
        "label": "Pro",
        "price_usd": 199,
        "chains": list(CHAINS.keys())[:50],
        "max_wallets": 5000,
        "features": ["basic_generation", "batch_generation", "hd_wallets", "vault", "mnemonic_convert",
                     "wp_plugin", "cli", "export", "shamir_backup", "sweep", "alerts", "webhooks",
                     "api_keys", "audit"],
    },
    "enterprise": {
        "label": "Enterprise",
        "price_usd": 499,
        "chains": list(CHAINS.keys()),
        "max_wallets": 100000,
        "features": ["all"],
    },
}


def get_chains_for_tier(tier: str) -> dict[str, ChainInfo]:
    tier_info = TIERS.get(tier, TIERS["free"])
    return {k: CHAINS[k] for k in tier_info["chains"] if k in CHAINS}


def validate_address(chain_key: str, address: str) -> bool:
    chain = CHAINS.get(chain_key)
    if not chain:
        return False
    import re
    return bool(re.match(chain.address_pattern, address))


# ── YAML Chain Loader ──────────────────────────────────────────────
# Users can define custom chains in chains.yaml (next to this file).
# Values merge on top of the defaults above. Override any field.

YAML_PATH = Path(__file__).parent / "chains.yaml"


def load_chains_yaml(path: Path = YAML_PATH) -> dict[str, ChainInfo]:
    """Load custom chain definitions from YAML, merged on top of defaults.

    Format:
        <key>:
          name: str
          family: str  (must match a ChainFamily value)
          symbol: str
          slip44: int
          hd_path: str
          decimals: int
          address_pattern: str
          explorer_url: str
          rpc_url: str
          curve: str
          native_token: str

    Returns dict of chain_key → ChainInfo. Empty dict if YAML not found.
    """
    if not path.exists():
        return {}

    try:
        import yaml
        data = yaml.safe_load(path.read_text())
    except ImportError:
        logger.warning("PyYAML not installed — cannot load chains.yaml")
        return {}
    except Exception as e:
        logger.error(f"Failed to load {path}: {e}")
        return {}

    if not isinstance(data, dict):
        return {}

    result: dict[str, ChainInfo] = {}
    for key, cfg in data.items():
        try:
            family_str = cfg.pop("family", "evm")
            family = ChainFamily(family_str)
            # Map YAML fields to ChainInfo constructor
            info = ChainInfo(
                key=key,
                name=cfg.get("name", key.upper()),
                family=family,
                symbol=cfg.get("symbol", key.upper()),
                slip44=int(cfg.get("slip44", 0)),
                hd_path=cfg.get("hd_path", ""),
                decimals=int(cfg.get("decimals", 18)),
                address_pattern=str(cfg.get("address_pattern", "")),
                explorer_url=cfg.get("explorer_url", ""),
                rpc_url=cfg.get("rpc_url", ""),
                curve=cfg.get("curve", "secp256k1"),
                native_token=cfg.get("native_token", ""),
                description=cfg.get("description", ""),
            )
            result[key] = info
        except Exception as e:
            logger.warning(f"Skipping chain '{key}' in {path}: {e}")

    return result


# Merge YAML chains on top of defaults
_yaml_chains = load_chains_yaml()
if _yaml_chains:
    CHAINS.update(_yaml_chains)
    logger.info(f"Merged {len(_yaml_chains)} chain(s) from {YAML_PATH}")
