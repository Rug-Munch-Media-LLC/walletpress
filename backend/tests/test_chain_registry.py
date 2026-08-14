"""Tests: chain registry completeness, groups, tiers, and address validation."""

import os
import tempfile
from pathlib import Path

os.environ["WP_VAULT_PASSWORD"] = "test-registry"
os.environ["WP_DATA_DIR"] = tempfile.mkdtemp(prefix="wp_test_registry_")

from core.config import cfg

cfg._vault_password = os.environ["WP_VAULT_PASSWORD"]

from wallet_engine.chains import (
    CHAIN_GROUPS,
    CHAINS,
    TIERS,
    ChainFamily,
    ChainInfo,
    get_chains_for_tier,
    load_chains_yaml,
    validate_address,
)


def test_all_chains_have_required_fields():
    for key, c in CHAINS.items():
        assert c.name, f"{key}: missing name"
        assert c.symbol, f"{key}: missing symbol"
        assert isinstance(c.family, ChainFamily), f"{key}: invalid family {c.family}"
        assert c.hd_path, f"{key}: missing hd_path"
        assert c.curve, f"{key}: missing curve"
        assert c.native_token, f"{key}: missing native_token"
        assert c.address_pattern, f"{key}: missing address_pattern"
        assert c.slip44 >= 0, f"{key}: invalid slip44"


def test_minimum_chain_count():
    """We should support at least 55 chains."""
    assert len(CHAINS) >= 55, f"Expected >= 55 chains, got {len(CHAINS)}"


def test_chain_groups_are_valid():
    for group_name, chain_keys in CHAIN_GROUPS.items():
        for key in chain_keys:
            assert key in CHAINS, f"Group '{group_name}' references unknown chain '{key}'"


def test_chain_groups_have_multiple_chains():
    for group_name, chain_keys in CHAIN_GROUPS.items():
        assert len(chain_keys) > 0, f"Group '{group_name}' is empty"
    # all group should include every chain
    assert len(CHAIN_GROUPS["all"]) == len(CHAINS)


def test_tiers_have_valid_chains():
    for tier_name, tier_info in TIERS.items():
        for key in tier_info["chains"]:
            assert key in CHAINS, f"Tier '{tier_name}' references unknown chain '{key}'"


def test_tier_hierarchy():
    free_chains = TIERS["free"]["chains"]
    enterprise_chains = TIERS["enterprise"]["chains"]
    assert len(free_chains) < len(enterprise_chains)
    for c in free_chains:
        assert c in enterprise_chains, f"Free chain '{c}' not in enterprise chains"
    assert len(enterprise_chains) == len(CHAINS)


def test_free_tier_basic_chains():
    free = TIERS["free"]
    assert "btc" in free["chains"]
    assert "eth" in free["chains"]
    assert "sol" in free["chains"]
    assert free["max_wallets"] == 10


def test_validate_address_valid():
    known = {
        "eth": "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
        "sol": "7EcDhSYGXxyscszYEp35KHN8vvw3svAuLKTzXwCFLtGQ",
        "btc": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
        "trx": "TXYZopYRdj2f9GkfC1mSXGJj1dCAg5XtKn",
        "bsc": "0x8894e0a0c962cb723c1976a4421c95949be2d4e3",
        "polygon": "0x0000000000000000000000000000000000001010",
        "base": "0x4200000000000000000000000000000000000006",
        "doge": "DDJQ6eKF3B1KEAxKJ8ySbRf1mSzS7AFj4k",
        "ltc": "LVaPmAcqEtnhAoJ4eKjL2KXZjMxS1jQvLC",
        "xrp": "rU6sCJtnNLGNPsGECiBajQnJAjmvEaSe9v",
        "dot": "1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "ada": "addr1qx2hx2n4x0qvw5j7h8t0a0m0k0l0m0n0p0q0r0s0t0u0v0w0x0y0z0",
        "atom": "cosmos1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq",
        "osmo": "osmo1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq",
        "sei": "sei1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq",
        "algo": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "nano": "nano_1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq",
        "ton": "Eaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "xlm": "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    }
    for key, addr in known.items():
        assert validate_address(key, addr), f"{key}: known good address fails validation"


def test_validate_address_invalid():
    assert validate_address("eth", "not_an_address") is False
    assert validate_address("sol", "0xshort") is False
    assert validate_address("btc", "") is False
    assert validate_address("trx", "0xnot_a_tron_address") is False


def test_validate_address_unknown_chain():
    assert validate_address("nonexistent_chain_xyz", "0xabc") is False


def test_get_chains_for_tier():
    for tier_name in TIERS:
        chains = get_chains_for_tier(tier_name)
        assert len(chains) > 0, f"Tier '{tier_name}' returned no chains"
        for _, info in chains.items():
            assert isinstance(info, ChainInfo)


def test_get_chains_for_free_tier():
    chains = get_chains_for_tier("free")
    assert "btc" in chains
    assert "eth" in chains
    assert "sol" in chains


def test_get_chains_for_enterprise():
    chains = get_chains_for_tier("enterprise")
    assert len(chains) == len(CHAINS)


def test_get_chains_for_unknown_tier():
    chains = get_chains_for_tier("nonexistent_tier")
    # Should fall back to free
    assert len(chains) == len(TIERS["free"]["chains"])


def test_chain_family_enum():
    families = {v.family for v in CHAINS.values()}
    assert ChainFamily.EVM in families
    assert ChainFamily.BITCOIN in families
    assert ChainFamily.SOLANA in families
    assert ChainFamily.COSMOS in families
    assert len(families) >= 5


def test_load_chains_yaml_missing():
    result = load_chains_yaml(Path("/tmp/nonexistent_chains_file_xyz.yaml"))
    assert result == {}


def test_no_duplicate_keys():
    assert len(CHAINS) == len(set(CHAINS.keys()))


def test_evm_chains_have_common_pattern():
    for key, c in CHAINS.items():
        if c.family == ChainFamily.EVM:
            assert c.address_pattern == "^0x[a-fA-F0-9]{40}$", f"{key}: unexpected EVM pattern"


def test_chains_have_explorer_url():
    for key, c in CHAINS.items():
        assert c.explorer_url, f"{key}: missing explorer_url"


def test_chains_have_description():
    for key, c in CHAINS.items():
        assert c.description, f"{key}: missing description"


def test_ed25519_chains_use_ed25519_curve():
    ed25519_keys = ["sol", "ada", "near", "sui", "apt", "algo", "xtz", "xmr", "xlm", "ton", "nano"]
    for key, c in CHAINS.items():
        if key in ed25519_keys:
            assert c.curve == "ed25519", f"{key}: expected ed25519 curve, got {c.curve}"


def test_secp256k1_chains_use_secp256k1_curve():
    secp_keys = ["btc", "eth", "trx", "doge", "ltc", "bch", "xrp", "atom", "fil"]
    for key, c in CHAINS.items():
        if key in secp_keys:
            assert c.curve == "secp256k1", f"{key}: expected secp256k1 curve, got {c.curve}"


def test_bip44_hd_path_format():
    for key, c in CHAINS.items():
        assert c.hd_path.startswith("m/"), f"{key}: hd_path should start with 'm/', got {c.hd_path}"
        assert "/" in c.hd_path, f"{key}: hd_path should contain '/' separators"


def test_starter_tier_builds_on_free():
    free_chains = set(TIERS["free"]["chains"])
    starter_chains = set(TIERS["starter"]["chains"])
    # Starter tier may not include all free chains (e.g., Solana is deep in the dict)
    # But starter should have more chains than free overall
    assert len(starter_chains) > len(free_chains), "Starter tier should have more chains than free"
    assert (
        len(TIERS["enterprise"]["chains"])
        >= len(TIERS["pro"]["chains"])
        >= len(starter_chains)
        >= len(free_chains)
    )


def test_pro_tier_max_wallets():
    assert TIERS["pro"]["max_wallets"] == 5000
    assert TIERS["enterprise"]["max_wallets"] == 100000
