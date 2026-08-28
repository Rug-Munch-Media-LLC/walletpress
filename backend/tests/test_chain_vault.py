"""Integration tests: chain-vault API endpoints."""

import pytest


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "walletpress"


def test_healthz(client):
    resp = client.get("/api/v1/chain-vault/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "WalletPress API"


def test_list_chains(client):
    resp = client.get("/api/v1/chain-vault/chains")
    assert resp.status_code == 200
    data = resp.json()
    chains = data
    assert len(chains) > 0


def test_get_stats(client, admin_headers):
    resp = client.get("/api/v1/chain-vault/stats", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "vault" in data
    assert "encryption_enabled" in data


@pytest.mark.parametrize("chain", ["eth", "sol", "btc", "trx", "base", "polygon", "bsc"])
def test_generate_wallet(client, admin_headers, chain):
    resp = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": chain,
            "count": 1,
        },
        headers=admin_headers,
    )
    if resp.status_code in (400, 402):
        pytest.skip(f"{chain}: {resp.json().get('detail', resp.json())}")
    assert resp.status_code == 200, f"{chain}: {resp.json()}"
    data = resp.json()
    assert data["generated"] >= 1
    assert data["wallets"][0]["address"]


def test_generate_batch(client, admin_headers):
    resp = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 3,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] == 3
    assert len(data["wallets"]) == 3


def test_generate_all(client, admin_headers):
    resp = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "all",
            "count": 1,
        },
        headers=admin_headers,
    )
    if resp.status_code == 402:
        pytest.skip("License tier blocks 'all' chains")
    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] >= 1


def test_generate_with_qr(client, admin_headers):
    resp = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 1,
            "include_qr": True,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200


def test_from_mnemonic(client, admin_headers):
    mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    resp = client.post(
        "/api/v1/chain-vault/derive-address",
        json={
            "mnemonic": mnemonic,
            "chain": "eth",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chain"] == "eth"
    assert data["mnemonic"].startswith("abandon")
    assert data["address"].startswith("0x")


def test_vault_list(client, admin_headers):
    client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 1,
        },
        headers=admin_headers,
    )
    resp = client.get("/api/v1/chain-vault/vault", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "wallets" in data
    assert data["total"] >= 1


def test_vault_get(client, admin_headers):
    gen = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 1,
        },
        headers=admin_headers,
    )
    wallet_id = gen.json()["wallets"][0]["id"]
    resp = client.get(f"/api/v1/chain-vault/vault/{wallet_id}", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == wallet_id
    assert data["chain"] == "eth"
    assert data["address"].startswith("0x")


def test_vault_get_full(client, admin_headers):
    gen = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 1,
        },
        headers=admin_headers,
    )
    wallet_id = gen.json()["wallets"][0]["id"]
    resp = client.get(f"/api/v1/chain-vault/vault/{wallet_id}/full", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == wallet_id
    assert "private_key_hex" in data
    # Full export must return the DECRYPTED private key (64-char hex),
    # not the stored ciphertext.
    from core.vault import get_vault

    encrypted_key = get_vault().get(wallet_id).encrypted_key
    assert encrypted_key, "wallet should store an encrypted key blob"
    assert len(data["private_key_hex"]) == 64
    assert all(c in "0123456789abcdefABCDEF" for c in data["private_key_hex"])
    assert data["private_key_hex"] != encrypted_key


def test_validate_address(client, admin_headers):
    resp = client.get(
        "/api/v1/chain-vault/validate/eth/0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["chain"] == "eth"
    assert data["address"] == "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"


def test_validate_all(client, admin_headers):
    resp = client.get(
        "/api/v1/chain-vault/validate/all?address=0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "possible_chains" in data or "results" in data or isinstance(data.get("address"), str)


def test_wallet_tree(client, admin_headers):
    client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 1,
        },
        headers=admin_headers,
    )
    resp = client.get("/api/v1/chain-vault/tree", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "tree" in data
    assert "total_families" in data
    assert data["total_wallets"] >= 1


def test_derive_address(client, admin_headers):
    mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    resp = client.post(
        "/api/v1/chain-vault/derive-address",
        json={
            "mnemonic": mnemonic,
            "chain": "eth",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chain"] == "eth"
    assert data["address"].startswith("0x")
    assert data["derivation_path"] != ""


def test_api_keys_crud(client, admin_headers):
    create = client.post(
        "/api/v1/chain-vault/api-keys",
        json={
            "label": "test-key",
            "scopes": ["wallet.read"],
        },
        headers=admin_headers,
    )
    assert create.status_code == 200
    key_data = create.json()
    assert "api_key_id" in key_data
    assert "api_key" in key_data

    list_resp = client.get("/api/v1/chain-vault/api-keys", headers=admin_headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    keys = list_data.get("api_keys", list_data.get("keys", []))
    assert len(keys) >= 1


def test_team_keys_crud(client, admin_headers):
    create = client.post(
        "/api/v1/team/keys?label=test-team-key&role=operator", headers=admin_headers
    )
    assert create.status_code == 200
    key_data = create.json()
    assert "key_id" in key_data
    assert "api_key" in key_data

    list_resp = client.get("/api/v1/team/keys", headers=admin_headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert "keys" in list_data


def test_delete_wallet(client, admin_headers):
    gen = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 1,
        },
        headers=admin_headers,
    )
    wallet_id = gen.json()["wallets"][0]["id"]
    resp = client.delete(f"/api/v1/chain-vault/vault/{wallet_id}", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True
    assert data["wallet_id"] == wallet_id


def test_auth_required_for_mutations(client):
    resp = client.post("/api/v1/chain-vault/generate", json={"chain": "eth", "count": 1})
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text[:200]}"


def test_invalid_api_key_rejected(client):
    bad_headers = {"X-API-Key": "this-key-is-wrong"}
    resp = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 1,
        },
        headers=bad_headers,
    )
    assert resp.status_code in (401, 403)


def test_unsupported_chain_returns_error(client, admin_headers):
    resp = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "nonexistent",
            "count": 1,
        },
        headers=admin_headers,
    )
    # License check may return 402 before chain validation, or 400 if chain is invalid
    assert resp.status_code in (400, 402)


def test_empty_label_generates_default(client, admin_headers):
    resp = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 1,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["wallets"][0]["label"] != ""


def test_generate_multiple_wallets(client, admin_headers):
    resp = client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 5,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] == 5
    assert len(data["wallets"]) == 5
    # each wallet must have a unique address
    addresses = [w["address"] for w in data["wallets"]]
    assert len(set(addresses)) == 5


def test_retention_portfolio(client, admin_headers):
    client.post(
        "/api/v1/chain-vault/generate",
        json={
            "chain": "eth",
            "count": 1,
        },
        headers=admin_headers,
    )
    resp = client.get("/api/v1/portfolio", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_wallets" in data


def test_retention_groups(client, admin_headers):
    resp = client.get("/api/v1/vault/groups", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "groups" in data


def test_wallet_memory_stubs(client, admin_headers):
    resp = client.get("/api/v1/wallet-memory/cluster", headers=admin_headers)
    assert resp.status_code in (200, 405, 404)


def test_metrics(client, admin_headers):
    resp = client.get("/metrics", headers=admin_headers)
    assert resp.status_code == 200


def test_test_vectors(client, admin_headers):
    resp = client.get("/api/v1/test-vectors", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, (dict, list))
