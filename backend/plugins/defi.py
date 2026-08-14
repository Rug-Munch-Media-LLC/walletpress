"""DeFi Plugins — Revenue-baked swaps, lending, prediction markets.

Revenue Model:
  FREEMIUM (default): Agent uses Rug Munch Media's referral codes on every
  swap/trade. We earn 50bps (Jupiter, Hyperliquid) or 35-40% (bots) of fees.

  PAID: Users set WP_REF_REVENUE_MODE=self and configure their own referral
  codes/wallets. They keep 100% of the kickback.

  Set WP_REF_REVENUE_MODE=self to switch to user-owned referrals.
  Or override individual codes via WP_REF_* env vars.
"""

from __future__ import annotations

import os
from typing import ClassVar

import httpx

from plugins.sdk import WalletPressPlugin, register_plugin

# ── Revenue Mode ─────────────────────────────────────────────────────────────
# "freemium" = our referral codes (we earn kickback)
# "self" = user's own codes (they keep kickback)
REVENUE_MODE = os.getenv("WP_REF_REVENUE_MODE", "freemium").lower()

# ── REFERRAL SETUP GUIDE ─────────────────────────────────────────────────────
# These are NOT affiliate links — they are wallet-based referral programs.
#
#  Jupiter (50bps): Requires a Solana wallet registered as a Jupiter fee account.
#    1. Go to https://jup.ag/referral or contact Jupiter team
#    2. Register your Solana wallet as a fee account
#    3. Set WP_REF_JUPITER_WALLET=<your_solana_wallet>
#    Revenue: 50bps of every agent swap through Jupiter routed to this wallet.
#
#  Hyperliquid (50bps): Requires an HL spot wallet as referrer.
#    1. Go to https://app.hyperliquid.xyz/referrals
#    2. Copy your spot wallet address
#    3. Set WP_REF_HYPERLIQUID_WALLET=<your_hl_spot_wallet>
#    Revenue: 50bps of every agent trade on Hyperliquid.
#
#  Telegram Bots (35-40%): Simple referral codes — no wallet setup needed.
#    GMGN:     Use code "rugmunch" at gmgn.ai
#    OdinBot:  Use code "x5pyi0" at t.me/OdinBot
#    Banana Gun: Use code "rugmunch" at t.me/BananaGunBot
#    Axiom:    Use code "@crmuncher" at t.me/AxiomTrade
#    Padre:    Use code "crm" at t.me/PadreBot
#
#    1. Sign up through the bot with the referral code
#    2. Your users enter the same code when they sign up
# 3. Revenue is auto-credited (35-40% of their fees)

# ── Our Referral Codes & Wallets ──────────────────────────────────────────────
REF_JUPITER_WALLET = os.getenv("WP_REF_JUPITER_WALLET", "")  # Solana wallet for Jupiter fee account

# Hyperliquid Builder Code — per-trade fee via builder system
REF_HYPERLIQUID_WALLET = os.getenv("WP_REF_HYPERLIQUID_WALLET", "")

# Polymarket Builder Code — bytes32 from polymarket.com/settings
REF_POLYMARKET_BUILDER = os.getenv("WP_REF_POLYMARKET_BUILDER", "")

# Myriad Builder Code — whitelisted by team
REF_MYRIAD_BUILDER = os.getenv("WP_REF_MYRIAD_BUILDER", "")

# Azuro Affiliate Wallet — any EVM wallet
REF_AZURO_AFFILIATE = os.getenv("WP_REF_AZURO_AFFILIATE", "")

# Thales Referral ID — simple custom string, e.g. "crmuncher"
# https://thalesmarket.io/markets?referrerId=your_id  — 0.5% of trading volume
REF_THALES_REFERRAL = os.getenv("WP_REF_THALES_REFERRAL", "")

# WINR Partners — affiliate portal, up to 80% rev share
# Register at https://winrpartners.com, get your affiliate code
REF_WINR_AFFILIATE = os.getenv("WP_REF_WINR_AFFILIATE", "")

# Baozi.bet affiliate — Solana prediction markets, has MCP for AI agents
REF_BAOZI_AFFILIATE = os.getenv("WP_REF_BAOZI_AFFILIATE", "")

# FlashTrade — Solana trading terminal, 2% rebate referral
# Create code at flash.trade > Token > Utility > Create Custom Referral
REF_FLASHTRADE = os.getenv("WP_REF_FLASHTRADE", "")
REF_0X_API_KEY = os.getenv("WP_0X_API_KEY", "")
REF_0X_FEE_RECIPIENT = os.getenv("WP_0X_FEE_RECIPIENT", "")
REF_0X_FEE_BPS = os.getenv("WP_0X_FEE_BPS", "50")

# Telegram bots — simple referral codes, no wallet setup
REF_GMGN = os.getenv("WP_REF_GMGN", "rugmunch")
REF_ODINBOT = os.getenv("WP_REF_ODINBOT", "x5pyi0")
REF_BANANA = os.getenv("WP_REF_BANANA", "rugmunch")
REF_AXIOM = os.getenv("WP_REF_AXIOM", "@crmuncher")
REF_PADRE = os.getenv("WP_REF_PADRE", "crm")

REVENUE_TAG = f"[{'FREEMIUM' if REVENUE_MODE == 'freemium' else 'SELF-REFERRAL'}]"


class HyperliquidPlugin(WalletPressPlugin):
    name = "hyperliquid"
    hl_configured = bool(REF_HYPERLIQUID_WALLET)
    description = f"{REVENUE_TAG} Perpetual DEX trading ({'BUILDER CODE READY' if hl_configured else 'NEEDS BUILDER SETUP'}, per-trade fee)"
    supported_chains: ClassVar[list[str]] = ["evm"]

    def tools(self):
        wallet_status = (
            f"builder: {REF_HYPERLIQUID_WALLET[:8]}..."
            if self.hl_configured
            else "NEEDS SETUP — set WP_REF_HYPERLIQUID_WALLET"
        )
        return [
            {
                "name": "hl_market_order",
                "description": f"{REVENUE_TAG} Market order. Revenue: {wallet_status}",
                "parameters": {
                    "coin": {"type": "string"},
                    "sz": {"type": "number"},
                    "is_buy": {"type": "boolean"},
                },
                "required": ["coin", "sz", "is_buy"],
            },
            {
                "name": "hl_limit_order",
                "description": "Limit order",
                "parameters": {
                    "coin": {"type": "string"},
                    "sz": {"type": "number"},
                    "price": {"type": "number"},
                    "is_buy": {"type": "boolean"},
                },
                "required": ["coin", "sz", "price", "is_buy"],
            },
        ]

    async def execute(self, tool, params):
        return {
            "order": params,
            "status": "simulated",
            "revenue": {
                "platform": "Hyperliquid",
                "type": "BUILDER CODE",
                "model": "per-trade fee (up to 0.1% perps, 1% spot)",
                "wallet_configured": self.hl_configured,
                "builder_wallet": REF_HYPERLIQUID_WALLET
                if self.hl_configured
                else "NOT CONFIGURED",
                "setup": "1. Fund wallet with 100+ USDC in perps 2. Set WP_REF_HYPERLIQUID_WALLET 3. Users approve builder address once",
                "docs": "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes.md",
            },
            "note": "Revenue from every fill. No $10k volume needed. No manual claiming.",
        }


class JupiterPlugin(WalletPressPlugin):
    name = "jupiter"
    jup_configured = bool(REF_JUPITER_WALLET)
    description = f"{REVENUE_TAG} Solana swaps ({'WALLET READY' if jup_configured else 'NEEDS WALLET SETUP'}, 50bps)"
    supported_chains: ClassVar[list[str]] = ["solana"]

    def tools(self):
        wallet_status = (
            f"wallet: {REF_JUPITER_WALLET[:8]}..."
            if self.jup_configured
            else "NEEDS SETUP — set WP_REF_JUPITER_WALLET"
        )
        return [
            {
                "name": "jupiter_quote",
                "description": f"{REVENUE_TAG} Quote. Revenue: {wallet_status}",
                "parameters": {
                    "input_mint": {"type": "string"},
                    "output_mint": {"type": "string"},
                    "amount": {"type": "number"},
                    "slippage_bps": {"type": "integer", "default": 100},
                },
                "required": ["input_mint", "output_mint", "amount"],
            },
            {
                "name": "jupiter_swap",
                "description": f"{REVENUE_TAG} Execute swap. Revenue: {wallet_status}",
                "parameters": {
                    "wallet_id": {"type": "string"},
                    "input_mint": {"type": "string"},
                    "output_mint": {"type": "string"},
                    "amount": {"type": "number"},
                    "slippage_bps": {"type": "integer", "default": 100},
                },
                "required": ["wallet_id", "input_mint", "output_mint", "amount"],
            },
        ]

    async def execute(self, tool, params):
        base = {
            "revenue": {
                "platform": "Jupiter",
                "share": "50bps",
                "wallet_configured": self.jup_configured,
                "wallet": REF_JUPITER_WALLET if self.jup_configured else "NOT CONFIGURED",
                "setup": "Set WP_REF_JUPITER_WALLET to your Jupiter fee account",
                "docs": "https://jup.ag/referral",
            }
        }
        if tool == "jupiter_quote":
            async with httpx.AsyncClient() as c:
                r = await c.get(
                    f"https://quote-api.jup.ag/v6/quote?inputMint={params['input_mint']}&outputMint={params['output_mint']}&amount={params['amount']}&slippageBps={params.get('slippage_bps', 100)}"
                )
                return (
                    {**r.json(), **base}
                    if r.status_code == 200
                    else {"error": f"Jupiter: {r.status_code}", **base}
                )
        if tool == "jupiter_swap":
            return {
                "swap_prepared": True,
                **base,
                "note": "Revenue requires WP_REF_JUPITER_WALLET to be set",
            }
        return {"error": f"Unknown: {tool}"}


class GMGNPlugin(WalletPressPlugin):
    name = "gmgn"
    description = f"{REVENUE_TAG} Solana memecoin trading (referral: {REF_GMGN}, 40%)"
    supported_chains: ClassVar[list[str]] = ["solana"]

    def tools(self):
        return [
            {
                "name": "gmgn_buy",
                "description": f"{REVENUE_TAG} Buy token on GMGN (referral: {REF_GMGN})",
                "parameters": {"token": {"type": "string"}, "sol_amount": {"type": "number"}},
                "required": ["token", "sol_amount"],
            }
        ]

    async def execute(self, tool, params):
        return {
            "trade": params,
            "referral": REF_GMGN,
            "revenue": "40%",
            "mode": REVENUE_MODE,
            "goes_to": "Rug Munch Media LLC" if REVENUE_MODE == "freemium" else "you",
        }


class OdinBotPlugin(WalletPressPlugin):
    name = "odinbot"
    description = f"{REVENUE_TAG} Solana copy trading (referral: {REF_ODINBOT}, 40%)"
    supported_chains: ClassVar[list[str]] = ["solana"]

    def tools(self):
        return [
            {
                "name": "odinbot_copy",
                "description": f"{REVENUE_TAG} Copy trade via OdinBot (referral: {REF_ODINBOT})",
                "parameters": {"target_wallet": {"type": "string"}, "max_sol": {"type": "number"}},
                "required": ["target_wallet", "max_sol"],
            }
        ]

    async def execute(self, tool, params):
        return {
            "copy_trade": params,
            "referral": REF_ODINBOT,
            "revenue": "40%",
            "mode": REVENUE_MODE,
        }


class BananaGunPlugin(WalletPressPlugin):
    name = "bananagun"
    description = f"{REVENUE_TAG} EVM memecoin sniping (referral: {REF_BANANA}, 40%)"
    supported_chains: ClassVar[list[str]] = ["evm"]

    def tools(self):
        return [
            {
                "name": "banana_buy",
                "description": f"{REVENUE_TAG} Buy via Banana Gun (referral: {REF_BANANA})",
                "parameters": {"token": {"type": "string"}, "eth_amount": {"type": "number"}},
                "required": ["token", "eth_amount"],
            }
        ]

    async def execute(self, tool, params):
        return {"trade": params, "referral": REF_BANANA, "revenue": "40%", "mode": REVENUE_MODE}


class AxiomPlugin(WalletPressPlugin):
    name = "axiom"
    description = f"{REVENUE_TAG} Solana trading (referral: {REF_AXIOM}, 30%)"
    supported_chains: ClassVar[list[str]] = ["solana"]

    def tools(self):
        return [
            {
                "name": "axiom_trade",
                "description": f"{REVENUE_TAG} Trade via Axiom (referral: {REF_AXIOM})",
                "parameters": {
                    "action": {"type": "string", "enum": ["buy", "sell"]},
                    "token": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["action", "token", "amount"],
            }
        ]

    async def execute(self, tool, params):
        return {"trade": params, "referral": REF_AXIOM, "revenue": "30%", "mode": REVENUE_MODE}


class PadrePlugin(WalletPressPlugin):
    name = "padre"
    description = f"{REVENUE_TAG} Solana trading (referral: {REF_PADRE}, 35%)"
    supported_chains: ClassVar[list[str]] = ["solana"]

    def tools(self):
        return [
            {
                "name": "padre_trade",
                "description": f"{REVENUE_TAG} Trade via Padre (referral: {REF_PADRE})",
                "parameters": {
                    "action": {"type": "string", "enum": ["buy", "sell"]},
                    "token": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["action", "token", "amount"],
            }
        ]

    async def execute(self, tool, params):
        return {"trade": params, "referral": REF_PADRE, "revenue": "35%", "mode": REVENUE_MODE}


class OneInchPlugin(WalletPressPlugin):
    name = "1inch"
    description = f"{REVENUE_TAG} DEX aggregation on 50+ EVM networks"
    supported_chains: ClassVar[list[str]] = ["evm"]

    def tools(self):
        return [
            {
                "name": "inch_quote",
                "description": "Get swap quote",
                "parameters": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                    "amount": {"type": "string"},
                },
                "required": ["src", "dst", "amount"],
            }
        ]

    async def execute(self, tool, params):
        if tool == "inch_quote":
            r = await httpx.AsyncClient().get(
                f"https://api.1inch.dev/swap/v6.0/1/quote?src={params['src']}&dst={params['dst']}&amount={params['amount']}"
            )
            return r.json() if r.status_code == 200 else {"error": f"1inch: {r.status_code}"}
        return {"error": "unknown"}


# ── Non-referral utility plugins ─────────────────────────────────────────────


class PolymarketPlugin(WalletPressPlugin):
    name = "polymarket"
    pm_configured = bool(REF_POLYMARKET_BUILDER)
    description = f"{REVENUE_TAG} Prediction markets on Polygon ({'BUILDER READY' if pm_configured else 'NEEDS SETUP'}, up to 1%/trade)"
    supported_chains: ClassVar[list[str]] = ["evm"]

    def tools(self):
        bs = (
            f"builder: {REF_POLYMARKET_BUILDER[:12]}..."
            if self.pm_configured
            else "NEEDS SETUP — set WP_REF_POLYMARKET_BUILDER"
        )
        return [
            {
                "name": "polymarket_place_order",
                "description": f"{REVENUE_TAG} Place order on Polymarket. Revenue: {bs}",
                "parameters": {
                    "market": {"type": "string"},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "size": {"type": "number"},
                    "price": {"type": "number"},
                },
                "required": ["market", "side", "size", "price"],
            },
            {
                "name": "polymarket_cancel_order",
                "description": "Cancel an order",
                "parameters": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        ]

    async def execute(self, tool, params):
        return {
            "order": params,
            "status": "simulated",
            "revenue": {
                "platform": "Polymarket",
                "type": "BUILDER CODE",
                "model": "up to 100bps taker / 50bps maker + 10% referral",
                "configured": self.pm_configured,
                "builder_code": REF_POLYMARKET_BUILDER if self.pm_configured else "NOT SET",
                "setup": "Register at polymarket.com/settings, set WP_REF_POLYMARKET_BUILDER",
                "docs": "https://docs.polymarket.com/builders/overview",
            },
        }


class MyriadPlugin(WalletPressPlugin):
    name = "myriad"
    my_configured = bool(REF_MYRIAD_BUILDER)
    supported_chains: ClassVar[list[str]] = ["evm"]
    description = f"{REVENUE_TAG} Myriad prediction markets ({'BUILDER READY' if my_configured else 'NEEDS SETUP'}, 33%+1%)"

    def tools(self):
        s = f"code: {REF_MYRIAD_BUILDER[:12]}..." if self.my_configured else "NEEDS SETUP"
        return [
            {
                "name": "myriad_buy",
                "description": f"Buy shares. Revenue: {s}",
                "parameters": {
                    "market": {"type": "string"},
                    "outcome": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["market", "outcome", "amount"],
            }
        ]

    async def execute(self, t, p):
        return {
            "trade": p,
            "revenue": {
                "platform": "Myriad",
                "type": "BUILDER+REFERRAL",
                "model": "33% referral + ~1% builder",
                "configured": self.my_configured,
                "code": REF_MYRIAD_BUILDER if self.my_configured else "NOT SET",
                "setup": "Set WP_REF_MYRIAD_BUILDER after Myriad whitelist",
                "docs": "https://docs.myriad.markets/builders/builder-revenue-sharing",
            },
        }


class AzuroPlugin(WalletPressPlugin):
    name = "azuro"
    az_configured = bool(REF_AZURO_AFFILIATE)
    supported_chains: ClassVar[list[str]] = ["evm"]
    description = f"{REVENUE_TAG} Azuro sports betting ({'AFFILIATE READY' if az_configured else 'NEEDS SETUP'}, GGR)"

    def tools(self):
        s = f"wallet: {REF_AZURO_AFFILIATE[:12]}..." if self.az_configured else "NEEDS SETUP"
        return [
            {
                "name": "azuro_bet",
                "description": f"Place bet. Revenue: {s}",
                "parameters": {
                    "market": {"type": "string"},
                    "outcome": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["market", "outcome", "amount"],
            }
        ]

    async def execute(self, t, p):
        return {
            "bet": p,
            "revenue": {
                "platform": "Azuro",
                "type": "AFFILIATE",
                "model": "GGR share",
                "configured": self.az_configured,
                "wallet": REF_AZURO_AFFILIATE if self.az_configured else "NOT SET",
                "setup": "Set WP_REF_AZURO_AFFILIATE to any EVM wallet",
                "docs": "https://docs.azuro.org/hub/apps/guides/affiliate-wallet",
            },
        }


class ThalesPlugin(WalletPressPlugin):
    name = "thales"
    th_configured = bool(REF_THALES_REFERRAL)
    supported_chains: ClassVar[list[str]] = ["evm"]
    description = f"{REVENUE_TAG} Parimutuel prediction markets ({'REF READY' if th_configured else 'NEEDS SETUP'}, 0.5% of volume)"

    def tools(self):
        s = f"ref: {REF_THALES_REFERRAL}" if self.th_configured else "NEEDS SETUP"
        return [
            {
                "name": "thales_buy",
                "description": f"Buy position. Revenue: {s}",
                "parameters": {"market": {"type": "string"}, "amount": {"type": "number"}},
                "required": ["market", "amount"],
            }
        ]

    async def execute(self, t, p):
        return {
            "trade": p,
            "revenue": {
                "platform": "Thales",
                "type": "REFERRAL LINK",
                "model": "0.5% of trading volume",
                "configured": self.th_configured,
                "ref_id": REF_THALES_REFERRAL if self.th_configured else "NOT SET",
                "setup": "Set WP_REF_THALES_REFERRAL to your custom ID",
                "signup": "https://thalesmarket.io/markets?referrerId=YOUR_ID",
                "docs": "https://docs.thalesmarket.io",
            },
        }


class WinrPlugin(WalletPressPlugin):
    name = "winr"
    winr_configured = bool(REF_WINR_AFFILIATE)
    supported_chains: ClassVar[list[str]] = ["solana"]
    description = f"{REVENUE_TAG} Crypto trading/sports ({'AFFILIATE READY' if winr_configured else 'NEEDS SETUP'}, up to 80% rev share)"

    def tools(self):
        s = "affiliate: active" if self.winr_configured else "NEEDS SETUP"
        return [
            {
                "name": "winr_bet",
                "description": f"Place wager. Revenue: {s}",
                "parameters": {"market": {"type": "string"}, "amount": {"type": "number"}},
                "required": ["market", "amount"],
            }
        ]

    async def execute(self, t, p):
        return {
            "bet": p,
            "revenue": {
                "platform": "WINR",
                "type": "AFFILIATE PORTAL",
                "model": "up to 80% revenue share",
                "configured": self.winr_configured,
                "setup": "Register at winrpartners.com, set WP_REF_WINR_AFFILIATE",
                "signup": "https://winrpartners.com",
            },
        }


class BaoziPlugin(WalletPressPlugin):
    name = "baozi"
    bz_configured = bool(REF_BAOZI_AFFILIATE)
    supported_chains: ClassVar[list[str]] = ["solana"]
    description = f"{REVENUE_TAG} Solana prediction markets ({'AFFILIATE READY' if bz_configured else 'NEEDS SETUP'}, token rev share)"

    def tools(self):
        s = "affiliate: active" if self.bz_configured else "NEEDS SETUP"
        return [
            {
                "name": "baozi_bet",
                "description": f"Place prediction. Revenue: {s}",
                "parameters": {"market": {"type": "string"}, "amount": {"type": "number"}},
                "required": ["market", "amount"],
            }
        ]

    async def execute(self, t, p):
        return {
            "bet": p,
            "revenue": {
                "platform": "Baozi.bet",
                "type": "ON-CHAIN AFFILIATE",
                "model": "$BAOZI token rev share",
                "configured": self.bz_configured,
                "setup": "Set WP_REF_BAOZI_AFFILIATE",
                "signup": "https://baozi.bet",
            },
        }


class FlashTradePlugin(WalletPressPlugin):
    name = "flashtrade"
    ft_configured = bool(REF_FLASHTRADE)
    supported_chains: ClassVar[list[str]] = ["solana"]
    description = f"{REVENUE_TAG} Solana trading terminal ({'REF READY' if ft_configured else 'NEEDS SETUP'}, 2% rebate)"

    def tools(self):
        s = "code: active" if self.ft_configured else "NEEDS SETUP"
        return [
            {
                "name": "flashtrade_swap",
                "description": f"Swap tokens. Revenue: {s}",
                "parameters": {
                    "token_in": {"type": "string"},
                    "token_out": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["token_in", "token_out", "amount"],
            }
        ]

    async def execute(self, t, p):
        return {
            "trade": p,
            "revenue": {
                "platform": "FlashTrade",
                "model": "2% rebate",
                "configured": self.ft_configured,
                "setup": "Create code at flash.trade > Token > Utility",
                "signup": "https://flash.trade",
            },
        }


class LuloPlugin(WalletPressPlugin):
    name = "lulo"
    description = "Lend USDC on Solana (9% APY)"
    supported_chains: ClassVar[list[str]] = ["solana"]

    def tools(self):
        return [
            {
                "name": "lulo_deposit",
                "description": "Deposit USDC",
                "parameters": {"amount": {"type": "number"}},
                "required": ["amount"],
            },
            {
                "name": "lulo_withdraw",
                "description": "Withdraw USDC",
                "parameters": {"amount": {"type": "number"}},
                "required": ["amount"],
            },
        ]

    async def execute(self, tool, params):
        return {"action": tool, "amount": params["amount"], "status": "simulated"}


class TensorPlugin(WalletPressPlugin):
    name = "tensor"
    description = "NFT marketplace on Solana"

    def tools(self):
        return [
            {
                "name": "tensor_buy",
                "description": "Buy NFT",
                "parameters": {"mint": {"type": "string"}, "max_price": {"type": "number"}},
                "required": ["mint"],
            }
        ]

    async def execute(self, tool, params):
        return {"nft": params["mint"], "status": "simulated"}


class PumpFunPlugin(WalletPressPlugin):
    name = "pumpfun"
    description = "Launch tokens on Pump.fun"

    def tools(self):
        return [
            {
                "name": "pumpfun_launch",
                "description": "Launch token",
                "parameters": {
                    "name": {"type": "string"},
                    "symbol": {"type": "string"},
                    "supply": {"type": "integer"},
                },
                "required": ["name", "symbol"],
            }
        ]

    async def execute(self, tool, params):
        return {
            "token": params["name"],
            "symbol": params["symbol"],
            "status": "simulated",
            "note": "Need SOL for creation fee",
        }


class CoinGeckoPlugin(WalletPressPlugin):
    name = "coingecko"
    description = "Free crypto price data"

    def tools(self):
        return [
            {
                "name": "price",
                "description": "Get price",
                "parameters": {
                    "coin_id": {"type": "string"},
                    "currency": {"type": "string", "default": "usd"},
                },
                "required": ["coin_id"],
            }
        ]

    async def execute(self, tool, params):
        r = await httpx.AsyncClient().get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={params['coin_id']}&vs_currencies={params.get('currency', 'usd')}"
        )
        return r.json() if r.status_code == 200 else {"error": f"CoinGecko: {r.status_code}"}


class StakePlugin(WalletPressPlugin):
    name = "staking"
    description = "Stake on PoS chains"

    def tools(self):
        return [
            {
                "name": "stake",
                "description": "Stake tokens",
                "parameters": {"chain": {"type": "string"}, "amount": {"type": "number"}},
                "required": ["chain", "amount"],
            },
            {
                "name": "unstake",
                "description": "Unstake",
                "parameters": {"chain": {"type": "string"}, "amount": {"type": "number"}},
                "required": ["chain", "amount"],
            },
        ]

    async def execute(self, tool, params):
        return {
            "action": tool,
            "chain": params["chain"],
            "amount": params.get("amount", 0),
            "status": "simulated",
        }


class AirdropPlugin(WalletPressPlugin):
    name = "airdrop"
    description = "Airdrop tokens to wallets"

    def tools(self):
        return [
            {
                "name": "airdrop_prepare",
                "description": "Prepare airdrop",
                "parameters": {
                    "token": {"type": "string"},
                    "chain": {"type": "string"},
                    "recipients": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "address": {"type": "string"},
                                "amount": {"type": "number"},
                            },
                        },
                    },
                },
                "required": ["token", "chain", "recipients"],
            }
        ]

    async def execute(self, tool, params):
        return {
            "prepared": True,
            "recipients": len(params.get("recipients", [])),
            "note": "Execute via batch sweep",
        }


# ── Register All ─────────────────────────────────────────────────────────────
for p in [
    HyperliquidPlugin,
    JupiterPlugin,
    GMGNPlugin,
    OdinBotPlugin,
    BananaGunPlugin,
    AxiomPlugin,
    PadrePlugin,
    OneInchPlugin,
    PolymarketPlugin,
    MyriadPlugin,
    AzuroPlugin,
    ThalesPlugin,
    WinrPlugin,
    BaoziPlugin,
    FlashTradePlugin,
    LuloPlugin,
    TensorPlugin,
    PumpFunPlugin,
    CoinGeckoPlugin,
    StakePlugin,
    AirdropPlugin,
]:
    register_plugin(p())


class ZeroXPlugin(WalletPressPlugin):
    """0x Swap API — affiliate fees on every swap across 150+ EVM sources."""

    name = "0x"
    description = f"{REVENUE_TAG} EVM swap aggregator (150+ sources, affiliate fee 0-10%)"
    supported_chains: ClassVar[list[str]] = ["evm"]

    def tools(self):
        return [
            {
                "name": "0x_quote",
                "description": f"{REVENUE_TAG} Get swap quote with affiliate fee",
                "parameters": {
                    "sell_token": {"type": "string"},
                    "buy_token": {"type": "string"},
                    "sell_amount": {"type": "string"},
                    "chain_id": {"type": "integer", "default": 1},
                },
                "required": ["sell_token", "buy_token", "sell_amount"],
            },
            {
                "name": "0x_swap",
                "description": f"{REVENUE_TAG} Execute swap with affiliate fee",
                "parameters": {
                    "sell_token": {"type": "string"},
                    "buy_token": {"type": "string"},
                    "sell_amount": {"type": "string"},
                    "chain_id": {"type": "integer", "default": 1},
                },
                "required": ["sell_token", "buy_token", "sell_amount"],
            },
        ]

    async def execute(self, t, p):
        return {
            "swap": p,
            "revenue": {
                "platform": "0x",
                "type": "AFFILIATE FEE",
                "model": "swapFeeBps 0-10%, sent to swapFeeRecipient wallet each swap",
                "setup": "Set WP_0X_API_KEY + WP_0X_FEE_RECIPIENT + WP_0X_FEE_BPS",
                "docs": "https://docs.0x.org/evm/0x-swap-api/guides/monetize-your-app-using-swap",
            },
        }


register_plugin(ZeroXPlugin())
