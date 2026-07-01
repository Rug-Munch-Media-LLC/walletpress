"""WalletPress Python SDK — pip install walletpress-sdk

Usage:
  from walletpress_sdk import WalletPress

  wp = WalletPress(api_key="wp_...", base_url="https://your-walletpress.com")
  wallet = wp.generate_wallet(chain="eth", label="my wallet")
  print(wallet.address, wallet.private_key)

  vault = wp.list_vault()
  for w in vault:
      print(w.address)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx


@dataclass
class Wallet:
    id: str
    chain: str
    address: str
    label: str = ""
    tags: list[str] = field(default_factory=list)
    private_key: str = ""
    mnemonic: str = ""
    public_key: str = ""
    derivation_path: str = ""
    encrypted: bool = False
    balance_usd: float = 0.0
    created_at: float = 0.0
    qr_png_base64: str = ""


@dataclass
class VaultStats:
    total_wallets: int
    by_chain: dict
    total_value_usd: float = 0.0


class WalletPress:
    """WalletPress API client — generate and manage wallets on 55 chains."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8010"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(headers={"X-API-Key": api_key, "Content-Type": "application/json"})

    def _get(self, path: str, params: dict = None):
        r = self._client.get(f"{self.base_url}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict = None):
        r = self._client.post(f"{self.base_url}{path}", json=data or {})
        r.raise_for_status()
        return r.json()

    # ── Wallet Generation ──────────────────────────────────

    def generate_wallet(self, chain: str, label: str = "", tags: list[str] = None,
                        count: int = 1, include_qr: bool = False) -> list[Wallet]:
        data = {"chain": chain, "label": label, "tags": tags or [], "count": count}
        result = self._post("/api/v1/chain-vault/generate", data)
        return [Wallet(**{
            **w, "qr_png_base64": w.get("qr_png_base64", ""),
            "private_key": w.get("private_key", ""),
        }) for w in result.get("wallets", [])]

    def generate_from_mnemonic(self, mnemonic: str, chains: list[str] = None) -> dict:
        return self._post("/api/v1/chain-vault/from-mnemonic", {
            "mnemonic": mnemonic, "chains": chains or [],
        })

    def import_key(self, chain: str, private_key: str, label: str = "") -> Wallet:
        result = self._post("/api/v1/chain-vault/import", {
            "chain": chain, "private_key": private_key, "label": label,
        })
        return Wallet(**result.get("wallet", {}))

    def import_csv(self, csv_path: str) -> dict:
        """Import wallets from a CSV file. Returns import report."""
        with open(csv_path, "rb") as f:
            r = self._client.post(
                f"{self.base_url}/api/v1/import/batch",
                files={"file": ("import.csv", f, "text/csv")},
            )
        return r.json()

    # ── Vault ──────────────────────────────────────────────

    def list_vault(self, chain: str = "", search: str = "",
                   limit: int = 100, offset: int = 0) -> list[Wallet]:
        result = self._get("/api/v1/chain-vault/vault", {
            "chain": chain, "search": search, "limit": limit, "offset": offset,
        })
        return [Wallet(**w) for w in result.get("wallets", [])]

    def get_wallet(self, wallet_id: str, include_key: bool = False,
                   include_qr: bool = False) -> Optional[Wallet]:
        result = self._get(f"/api/v1/chain-vault/vault/{wallet_id}", {
            "include_key": str(include_key).lower(),
            "include_qr": str(include_qr).lower(),
        })
        return Wallet(**result) if "id" in result else None

    def get_portfolio(self) -> dict:
        return self._get("/api/v1/portfolio")

    def get_health(self) -> dict:
        return self._get("/api/v1/chain-vault/healthz")

    def get_stats(self) -> VaultStats:
        result = self._get("/api/v1/chain-vault/stats")
        return VaultStats(**result.get("vault", {}))

    # ── Validation ─────────────────────────────────────────

    def validate_address(self, address: str, chain: str) -> dict:
        return self._get(f"/api/v1/chain-vault/validate/{chain}/{address}")

    def seed_repair(self, partial_mnemonic: str) -> dict:
        return self._post("/api/v1/tool/seed-repair", {"mnemonic": partial_mnemonic})

    def get_compatibility(self, wallet_id: str) -> dict:
        return self._get(f"/api/v1/wallet/{wallet_id}/compatibility")

    def get_gas_estimate(self, wallet_id: str) -> dict:
        return self._get(f"/api/v1/wallet/{wallet_id}/gas-estimate")

    # ── Groups ─────────────────────────────────────────────

    def list_groups(self) -> list:
        return self._get("/api/v1/vault/groups").get("groups", [])

    def set_group(self, wallet_id: str, group: str) -> dict:
        return self._post(f"/api/v1/vault/{wallet_id}/group?group={group}")

    # ── Maintenance ────────────────────────────────────────

    def backup(self, output_path: str):
        wallets = self.list_vault(limit=100000)
        with open(output_path, "w") as f:
            json.dump({
                "version": "1.1.0",
                "exported_at": time.time(),
                "wallets": [{
                    "id": w.id, "chain": w.chain, "address": w.address,
                    "label": w.label, "encrypted_key": w.private_key,
                } for w in wallets if w.private_key],
            }, f, indent=2)
        return {"exported": len(wallets), "path": output_path}
