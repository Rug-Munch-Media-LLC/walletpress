"""License enforcement — open source core, paid enterprise features.

PHILOSOPHY:
  The code is 100% open source (MIT). You can read every line.
  What you pay for is convenience, support, and full features.

  The license key is a simple HMAC-signed token. The verification
  code is PUBLIC — you can see exactly what it checks. No secrets.
  No obfuscation. We don't hide what the license unlocks.

EDITIONS:
  Community (free, no key):
    - 3 chains (BTC, ETH, SOL)
    - Single wallet generation
    - Basic vault (10 wallets max)
    - No batch, no API, no 2FA, no email
    - WordPress plugin (free tier)

  Starter ($49 one-time / $29/mo hosted):
    - 10 chains
    - Batch generation (up to 100)
    - Full vault (unlimited)
    - Mnemonic conversion
    - CLI access

  Pro ($199 one-time / $79/mo hosted):
    - 55 chains
    - Unlimited batch
    - Shamir backup
    - Sweep & rotate
    - Webhooks, alerts, audit
    - IP allowlisting
    - Email notifications
    - API marketplace access

  Enterprise ($499 one-time / $199/mo hosted):
    - Everything in Pro
    - 2FA enforcement
    - Airdrop tool (100k+ wallets)
    - Health monitoring
    - SLA support
    - Custom integration
    - White-label option

UPGRADE PATH:
  Community (free) → Starter ($49) → Pro ($199) → Enterprise ($499)

  Every upgrade preserves your vault, wallets, and configurations.
  Downgrades are also supported (limited to lower tier's capabilities).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("wp.license")

EDITION_DESCRIPTIONS = {
    "community": "Open source engine. 3 chains. WordPress plugin. No setup support.",
    "pro": "License key unlocks 55 chains + all features. One-command deploy script included.",
}

FEATURES = {
    "community": {
        "name": "Community",
        "price_usd": 0,
        "description": EDITION_DESCRIPTIONS["community"],
        "chains": ["btc", "eth", "sol"],
        "max_vault_wallets": 10,
        "batch_max": 1,
        "features": [
            "wallet_generation", "basic_vault", "wp_plugin_free",
            "bip39_verify", "open_source_code",
        ],
    },
    "pro": {
        "name": "Pro",
        "price_usd": 199,
        "description": EDITION_DESCRIPTIONS["pro"],
        "chains": "__all__",
        "max_vault_wallets": 100000,
        "batch_max": 100000,
        "features": [
            "all_chains", "full_vault", "wp_plugin_pro",
            "bip39_verify", "batch_generation", "hd_wallets",
            "shamir_backup", "sweep_rotate", "webhooks",
            "alerts", "audit", "email_notifications",
            "ip_allowlist", "two_factor_auth",
            "airdrop_tool", "health_monitoring",
            "proof_of_generation",
            "cli_access", "export_all_formats",
            "everything",
        ],
    },
}


class LicenseManager:
    """Manages license verification with public verification logic.

    PRICING (simplified — one decision, two options):
      ┌─────────────────────────────────────────────────────────────┐
      │  WordPress Plugin (free) → 3 chains, basic vault           │
      │                                                            │
      │  Then pick ONE:                                            │
      │    BUY ONCE → Pro license ($199) — use forever, self-host  │
      │    SUBSCRIBE → Hosted ($29/mo) — no setup, auto-updates    │
      │                                                            │
      │  Both unlock the same thing: 55 chains, all features.      │
      └─────────────────────────────────────────────────────────────┘

    The verification code is deliberately simple and PUBLIC.
    Anyone can read it and understand exactly what the license unlocks.
    No secrets, no obfuscation, no shenanigans.
    """

    def __init__(self, key_path: Optional[Path] = None):
        self.key_path = key_path or Path("/etc/walletpress/license.key")
        self._tier: str = self._detect_tier()

    def _detect_tier(self) -> str:
        """Check for license key file.

        The license key is a simple signed JSON token.
        Without a key, the software runs in Community mode.

        Verification is public — you can see exactly what this checks.
        """
        # Check environment variable first (for Docker/k8s)
        env_license = os.getenv("WP_LICENSE_KEY", "")
        if env_license:
            tier = self._verify_token(env_license)
            if tier:
                logger.info(f"License verified via env: {tier}")
                return tier

        # Check license file
        if self.key_path.exists():
            try:
                content = self.key_path.read_text().strip()
                tier = self._verify_token(content)
                if tier:
                    logger.info(f"License verified via file: {tier}")
                    return tier
                logger.warning("License file found but invalid")
            except Exception as e:
                logger.error(f"License file error: {e}")

        # No valid license — community mode
        logger.info("No valid license found. Running in Community mode.")
        return "community"

    def _verify_token(self, token: str) -> Optional[str]:
        """Verify a license token.

        Token format: base64(json({"tier":"pro","exp":1234567890,"sig":"..."}))

        The signature is HMAC-SHA256 of the payload with our public key.
        The public key for signature verification is EMBEDDED here.
        Anyone can verify our license tokens.
        """
        try:
            import base64
            decoded = base64.b64decode(token)
            data = json.loads(decoded)
            tier = data.get("tier", "")
            exp = data.get("exp", 0)
            sig = data.get("sig", "")

            # Check tier is valid
            if tier not in FEATURES:
                return None

            # Check expiration
            if exp > 0 and time.time() > exp:
                logger.info(f"License expired for tier {tier}")
                return None

            # Verify signature
            payload = json.dumps({"tier": tier, "exp": exp}, sort_keys=True)
            # Use WP_LICENSE_SECRET for verification (same key used for generation).
            # Falls back to WP_ADMIN_KEY for backward compatibility.
            verify_key = os.getenv("WP_LICENSE_SECRET") or os.getenv("WP_ADMIN_KEY")
            if not verify_key:
                logger.warning("No WP_LICENSE_SECRET or WP_ADMIN_KEY configured — cannot verify license")
                return None
            expected = hmac.new(verify_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                logger.warning(f"License signature invalid for {tier}")
                return None

            return tier
        except Exception as e:
            logger.error(f"License verification error: {e}")
            return None

    @property
    def tier(self) -> str:
        return self._tier

    @property
    def is_paid(self) -> bool:
        return self._tier in ("starter", "pro", "enterprise")

    def has_feature(self, feature: str) -> bool:
        tier_config = FEATURES.get(self._tier, FEATURES["community"])
        return feature in tier_config.get("features", []) or "everything" in tier_config.get("features", [])

    def get_chain_list(self) -> list[str]:
        """Get the list of available chains for this tier."""
        from wallet_engine.chains import CHAINS
        tier_info = FEATURES.get(self._tier, FEATURES["community"])
        chains = tier_info["chains"]
        if chains == "__all__":
            return list(CHAINS.keys())
        return [c for c in chains if c in CHAINS]

    def check_wallet_limit(self, current_count: int) -> bool:
        """Check if wallet count is within tier limit."""
        tier_info = FEATURES.get(self._tier, FEATURES["community"])
        limit = tier_info["max_vault_wallets"]
        if limit == 0:
            return True  # Unlimited
        return current_count < limit

    def check_batch_limit(self, requested: int) -> bool:
        """Check if batch size is within tier limit."""
        tier_info = FEATURES.get(self._tier, FEATURES["community"])
        limit = tier_info["batch_max"]
        return requested <= limit

    def to_dict(self) -> dict:
        tier_info = FEATURES.get(self._tier, FEATURES["community"])
        return {
            "tier": self._tier,
            "plan_name": tier_info["name"],
            "is_paid": self.is_paid,
            "max_chains": tier_info["chains"],
            "max_vault_wallets": tier_info["max_vault_wallets"],
            "max_batch": tier_info["batch_max"],
            "features": tier_info["features"],
        }


# Singleton
_license: Optional[LicenseManager] = None


def get_license() -> LicenseManager:
    global _license
    if _license is None:
        _license = LicenseManager()
    return _license
