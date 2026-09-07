"""Wallet & vault tools for the WalletPress AI Agent.

Wallet generation/derivation, vault management, balances, rotation, and
sweeping (including the EVM sweep implementation `_evm_sweep` which the
agent scheduler imports via `agent.mcp_server`).

All WRITE tools go through the shared HITL helper `_write_with_hitl`.
"""

from __future__ import annotations

import time

from agent.mcp.instance import _write_with_hitl, logger, mcp
from core.agent_safety import audit_log, check_address, check_spending_limit, record_spending
from core.config import cfg
from core.vault import WalletEntry, get_vault

# ── WALLET GENERATION ──────────────────────────────────────


@mcp.tool()
def wallet_generate(chain: str, label: str = "", count: int = 1) -> dict:
    """Generate one or more wallets for any supported chain.

    Args:
        chain: Chain key (eth, sol, btc, trx, bsc, polygon, base, ...)
        label: Optional human-readable label
        count: Number of wallets to generate (default 1, max 100)
    """
    hitl = _write_with_hitl(
        "wallet_generate",
        {"chain": chain, "label": label, "count": count},
        f"Generate {count} wallet(s) on {chain}",
    )
    if "confirmation_id" in hitl:
        return hitl
    from wallet_engine.generator import get_generator

    vault = get_vault()
    generator = get_generator(cfg.vault_password)
    wallets = []
    created_ids = []
    try:
        for i in range(count):
            lbl = label or f"{chain}_{i + 1}_{int(time.time())}"
            try:
                wallet = generator.generate(chain, label=lbl)
            except ValueError as e:
                # P2-3: roll back any partial inserts so caller doesn't see
                # inconsistent state (e.g. 5 of 10 wallets persisted, error
                # in the middle, caller doesn't know which were saved).
                for wid in created_ids:
                    vault.delete(wid)
                return {"error": str(e), "rolled_back": created_ids}
            entry = WalletEntry(
                id=f"wp_agent_{chain}_{int(time.time() * 1000)}_{i}",
                chain=wallet.chain,
                address=wallet.address,
                label=wallet.label,
                tags=wallet.tags,
                created_at=wallet.created_at,
                encrypted_key=wallet.private_key_hex if wallet.encrypted else "",
                public_key=wallet.public_key_hex,
                derivation_path=wallet.derivation_path,
                encrypted=wallet.encrypted,
            )
            vault.put(entry)
            created_ids.append(entry.id)
            wallets.append(
                {
                    "id": entry.id,
                    "chain": entry.chain,
                    "address": entry.address,
                    "label": entry.label,
                }
            )
    except Exception as e:
        # Any unexpected error — roll back partial inserts.
        for wid in created_ids:
            vault.delete(wid)
        return {"error": f"{type(e).__name__}: {e}", "rolled_back": created_ids}
    return {"generated": len(wallets), "wallets": wallets}


@mcp.tool()
def wallet_from_mnemonic(mnemonic: str, chains: list[str] | None = None) -> dict:
    """Derive wallets from a BIP39 mnemonic phrase.

    Args:
        mnemonic: BIP39 seed phrase (12 or 24 words)
        chains: List of chains to derive (empty = all 55 chains)
    """
    hitl = _write_with_hitl(
        "wallet_from_mnemonic", {"chains": chains}, "Derive wallets from a mnemonic phrase"
    )
    if hitl:
        return hitl
    from wallet_engine.chains import CHAINS
    from wallet_engine.generator import get_generator

    vault = get_vault()
    generator = get_generator(cfg.vault_password)
    chain_list = chains or list(CHAINS.keys())
    results = {}
    for ck in chain_list:
        try:
            wallet = generator.generate(ck, mnemonic=mnemonic, label=f"mnemonic_{ck}")
        except ValueError:
            results[ck] = {"error": "chain not supported"}
            continue
        entry = WalletEntry(
            id=f"wp_mcp_mnemonic_{ck}_{int(time.time())}",
            chain=wallet.chain,
            address=wallet.address,
            label=wallet.label,
            tags=[*wallet.tags, "from_mnemonic"],
            created_at=wallet.created_at,
            encrypted_key=wallet.private_key_hex if wallet.encrypted else "",
            public_key=wallet.public_key_hex,
            derivation_path=wallet.derivation_path,
            encrypted=wallet.encrypted,
        )
        vault.put(entry)
        results[ck] = {"address": entry.address, "wallet_id": entry.id}
    return {"derived_for": len(results), "chains": results}


# ── VAULT MANAGEMENT ───────────────────────────────────────


@mcp.tool()
def vault_list(chain: str = "", limit: int = 50) -> list[dict]:
    """List wallets in the vault (no private keys returned).

    Args:
        chain: Optional filter by chain
        limit: Max results (default 50)
    """
    vault = get_vault()
    wallets = vault.list(chain=chain, limit=limit) if chain else vault.list(limit=limit)
    return [
        {
            "id": w.id,
            "chain": w.chain,
            "address": w.address,
            "label": w.label,
            "tags": w.tags,
            "created_at": w.created_at,
            "encrypted": w.encrypted,
            "balance_usd": w.balance_usd,
        }
        for w in wallets
    ]


@mcp.tool()
def vault_get(wallet_id: str, include_private_key: bool = False) -> dict:
    """Get wallet details from the vault.

    By default returns only public info (address, public_key, derivation_path).
    Private key export requires explicit opt-in via include_private_key=True
    AND goes through HITL confirmation. This is the LAST line of defense
    before a plaintext key leaves the process — never bypass it.

    P2-4 fix: Previously the function unconditionally decrypted and returned
    the private key, with no audit trail of the export beyond the agent
    audit (which the caller controls). Now:
      - Default: returns public info only (no private key field at all)
      - include_private_key=True: requires HITL confirmation
      - Every export logged via audit_log with explicit 'key_export' tag

    Args:
        wallet_id: Wallet ID from vault_list
        include_private_key: Set True to export the decrypted private key
    """
    vault = get_vault()
    wallet = vault.get(wallet_id)
    if not wallet:
        return {"error": f"Wallet {wallet_id} not found"}

    result = {
        "id": wallet.id,
        "chain": wallet.chain,
        "address": wallet.address,
        "label": wallet.label,
        "tags": wallet.tags,
        "created_at": wallet.created_at,
        "public_key": wallet.public_key,
        "derivation_path": wallet.derivation_path,
        "encrypted": wallet.encrypted,
        "balance_usd": wallet.balance_usd,
        "private_key_exported": False,
    }

    if not include_private_key:
        return result

    # Private key export requires HITL confirmation. This is a destructive
    # operation — the caller is about to receive a plaintext key.
    hitl = _write_with_hitl(
        "key_export",
        {"wallet_id": wallet_id, "chain": wallet.chain, "address": wallet.address},
        f"Export private key for {wallet.chain} wallet {wallet.address[:12]}...",
    )
    if "confirmation_id" in hitl:
        return hitl

    if wallet.encrypted_key and wallet.encrypted and cfg.vault_password:
        from wallet_engine.generator import get_generator

        generator = get_generator(cfg.vault_password)
        result["private_key"] = generator.decrypt_key(wallet.encrypted_key)
        result["private_key_exported"] = True
        audit_log(
            "key_export",
            {"wallet_id": wallet_id, "chain": wallet.chain, "address": wallet.address},
            {"status": "exported"},
            confirmed_by="human",
        )
        logger.warning(
            f"Private key exported for wallet {wallet_id} ({wallet.chain}, {wallet.address[:12]}...)"
        )
    elif wallet.encrypted_key:
        # Encrypted but we have no KEK. Return encrypted form, not the raw key.
        result["private_key_encrypted"] = wallet.encrypted_key
        result["note"] = (
            "Wallet is encrypted but vault password is not set in this "
            "process. Cannot decrypt. Set WP_VAULT_PASSWORD or configure the "
            "file-based KEK."
        )
    return result


@mcp.tool()
def vault_delete(wallet_id: str) -> dict:
    """Delete a wallet permanently.

    Args:
        wallet_id: Wallet ID to delete
    """
    hitl = _write_with_hitl(
        "vault_delete", {"wallet_id": wallet_id}, f"Permanently delete wallet {wallet_id}"
    )
    if hitl:
        return hitl
    vault = get_vault()
    if vault.delete(wallet_id):
        return {"deleted": True, "wallet_id": wallet_id}
    return {"error": f"Wallet {wallet_id} not found"}


@mcp.tool()
def vault_stats() -> dict:
    """Get vault statistics — total wallets, encrypted count, chains used, rotations."""
    vault = get_vault()
    return vault.stats()


# ── BALANCE & ANALYSIS ─────────────────────────────────────


@mcp.tool()
async def balance_check(chain: str, address: str) -> dict:
    """Check wallet balance on any supported chain.

    Args:
        chain: Chain key (eth, sol, btc, trx, ...)
        address: Wallet address
    """
    from routers.balance_fetcher import fetch_balance

    return await fetch_balance(chain, address)


@mcp.tool()
def vault_balances(chain: str = "") -> dict:
    """Get balances for all wallets in the vault.

    Args:
        chain: Optional chain filter
    """
    vault = get_vault()
    wallets = vault.list(chain=chain, limit=500) if chain else vault.list(limit=500)
    return {
        "wallets": [
            {"id": w.id, "chain": w.chain, "address": w.address, "balance_usd": w.balance_usd}
            for w in wallets
        ],
        "total_usd": sum(w.balance_usd for w in wallets),
        "wallet_count": len(wallets),
    }


# ── WALLET MANAGEMENT ──────────────────────────────────────


@mcp.tool()
def wallet_rotate(wallet_id: str, reason: str = "agent_rotation") -> dict:
    """Rotate a wallet to a new address. Old wallet preserved with 'rotated' tag.

    Args:
        wallet_id: ID of existing wallet
        reason: Rotation reason
    """
    hitl = _write_with_hitl(
        "wallet_rotate",
        {"wallet_id": wallet_id, "reason": reason},
        f"Rotate keys for wallet {wallet_id}: {reason}",
    )
    if hitl:
        return hitl
    from wallet_engine.generator import get_generator

    vault = get_vault()
    old = vault.get(wallet_id)
    if not old:
        return {"error": f"Wallet {wallet_id} not found"}
    generator = get_generator(cfg.vault_password)
    new = generator.generate(
        old.chain, label=f"rotation_{old.chain}_{int(time.time())}", tags=["rotated", "active"]
    )
    new_entry = WalletEntry(
        id=f"wp_rot_{old.chain}_{int(time.time())}",
        chain=new.chain,
        address=new.address,
        label=new.label,
        tags=new.tags,
        created_at=new.created_at,
        encrypted_key=new.private_key_hex if new.encrypted else "",
        public_key=new.public_key_hex,
        derivation_path=new.derivation_path,
        encrypted=new.encrypted,
    )
    vault.put(new_entry)
    vault.record_rotation(old.id, new.address, reason=reason)
    return {
        "rotated": True,
        "old_wallet_id": old.id,
        "old_address": old.address,
        "new_wallet_id": new_entry.id,
        "new_address": new_entry.address,
        "chain": old.chain,
    }


@mcp.tool()
def wallet_sweep(from_wallet_id: str, to_address: str) -> dict:
    """Sweep ALL funds from a vault wallet to an external address.

    Implements actual on-chain transfer for EVM chains (Ethereum, Base,
    Polygon, Arbitrum, Optimism, BNB Chain, Avalanche, Fantom, Gnosis, etc.).
    For non-EVM chains (Solana, TRON, BTC family), returns a clear
    "not implemented" error with the transaction params the caller can sign.

    Security checks performed BEFORE signing:
      1. Address allow/block list (block known scam addresses)
      2. Spending limits (per-chain, per-period)
      3. HITL confirmation (human must approve via agent_confirm)

    Args:
        from_wallet_id: Source wallet ID from vault
        to_address: Destination address (must be valid for the chain)
    """
    from routers.balance_fetcher import EVM_RPC

    # Address safety check
    vault = get_vault()
    wallet = vault.get(from_wallet_id)
    if not wallet:
        return {"error": f"Wallet {from_wallet_id} not found"}
    chain = wallet.chain
    addr_check = check_address(to_address, chain)
    if not addr_check["allowed"]:
        return {"error": f"Address blocked: {addr_check['reason']}"}

    # Spending limit check — uses the REAL on-chain balance as the proposed
    try:
        import asyncio

        from routers.balance_fetcher import fetch_balance

        bal = asyncio.run(fetch_balance(chain, wallet.address))
        spend_amount = float(bal.get("balance_decimal", 0) or 0)
        if bal.get("error") or bal.get("source") in ("unsupported", "no-rpc"):
            return {
                "error": (
                    f"Cannot verify on-chain balance for {chain} — refusing to "
                    "sweep without a verified amount for the spending-limit check"
                )
            }
    except Exception as e:
        return {"error": f"Balance verification failed: {e}"}

    limit_check = check_spending_limit(chain, spend_amount)
    if not limit_check["allowed"]:
        return {"error": f"Spending limit exceeded: {limit_check['exceeded']}"}

    hitl = _write_with_hitl(
        "wallet_sweep",
        {"from_wallet_id": from_wallet_id, "to_address": to_address},
        f"Sweep funds from {from_wallet_id} to {to_address}",
    )
    if hitl:
        return hitl

    # EVM chain: build, sign, and broadcast via tx_broadcaster
    if chain in EVM_RPC:
        return _evm_sweep(wallet, to_address, chain)

    # Non-EVM: return intent + clear "not implemented" notice
    return {
        "status": "intent_only",
        "chain": chain,
        "wallet_id": from_wallet_id,
        "from_address": wallet.address,
        "to_address": to_address,
        "note": (
            f"Auto-broadcast not yet implemented for {chain}. "
            f"Sign the transaction externally with the wallet's private key "
            f"and broadcast via tx_broadcaster.broadcast()."
        ),
    }


def _evm_sweep(wallet, to_address: str, chain: str) -> dict:
    """Build, sign, and broadcast an EVM sweep transaction.

    Returns the tx_hash on success or an error dict on failure.
    """
    import asyncio

    from core.balance_fetcher import EVM_RPC
    from eth_account import Account
    from web3 import Web3
    from web3.exceptions import Web3Exception

    from routers.tx_broadcaster import _evm_broadcast

    rpc_url = EVM_RPC.get(chain)
    if not rpc_url:
        return {"error": f"No RPC configured for chain {chain}"}

    # Decrypt the private key from the vault
    from wallet_engine.generator import get_generator

    gen = get_generator(cfg.vault_password)
    if not wallet.encrypted_key or not wallet.encrypted:
        return {"error": f"Wallet {wallet.id} has no encrypted key (client-side only?)"}
    try:
        privkey_hex = gen.decrypt_key(wallet.encrypted_key)
    except Exception as e:
        return {"error": f"Failed to decrypt private key: {e}"}

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
        if not w3.is_connected():
            return {"error": f"Cannot connect to RPC for {chain}"}

        account = Account.from_key(privkey_hex)
        nonce = w3.eth.get_transaction_count(account.address)
        gas_price = w3.eth.gas_price
        chain_id = w3.eth.chain_id

        # Get balance — sweep = balance - gas
        balance_wei = w3.eth.get_balance(account.address)
        # Estimate gas for a simple transfer (21k) + buffer
        gas_limit = 21000
        gas_cost_wei = gas_limit * gas_price
        if balance_wei <= gas_cost_wei:
            return {
                "error": "Insufficient balance to cover gas",
                "balance_wei": balance_wei,
                "gas_cost_wei": gas_cost_wei,
            }

        value_wei = balance_wei - gas_cost_wei

        # Build the transaction
        tx = {
            "nonce": nonce,
            "to": to_address,
            "value": value_wei,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": chain_id,
        }

        # Sign
        signed = account.sign_transaction(tx)

        # Broadcast via existing tx_broadcaster helper (handles errors uniformly)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_evm_broadcast(chain, signed.raw_transaction.hex()))
        finally:
            loop.close()

        if result.get("broadcast"):
            # Record the spending
            try:
                amount_eth = float(w3.from_wei(value_wei, "ether"))
                record_spending(chain, amount_eth)
            except Exception as e:
                logger.debug(f"record_spending failed after sweep: {e}")
            audit_log(
                "wallet_sweep",
                {"from_wallet_id": wallet.id, "to_address": to_address, "chain": chain},
                {"tx_hash": result["tx_hash"], "amount_wei": value_wei},
                confirmed_by="human",
            )
            return {
                "status": "broadcast",
                "chain": chain,
                "from_wallet_id": wallet.id,
                "from_address": wallet.address,
                "to_address": to_address,
                "tx_hash": result["tx_hash"],
                "amount_wei": value_wei,
                "amount_native": float(w3.from_wei(value_wei, "ether")),
                "gas_cost_wei": gas_cost_wei,
                "explorer_url": f"https://etherscan.io/tx/{result['tx_hash']}"
                if chain == "eth"
                else None,
            }
        else:
            return {
                "error": f"Broadcast failed: {result.get('error', 'unknown')}",
                "chain": chain,
            }
    except Web3Exception as e:
        return {"error": f"Web3 error: {e}", "chain": chain}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "chain": chain}
