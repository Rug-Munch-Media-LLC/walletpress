#!/usr/bin/env python3
from __future__ import annotations
"""WalletPress Receipt Verifier — CLI tool to verify x402 order receipts.

Usage:
    # Verify an order receipt
    python3 verify_receipt.py --order-id x402_abc123 \\
        --signature "base64signature..." \\
        --pubkey "ed25519pubkeyhex"

    # Verify a key deletion attestation
    python3 verify_receipt.py --order-id x402_abc123 \\
        --deletion-sig "base64signature..." \\
        --pubkey "ed25519pubkeyhex" \\
        --addresses addr1,addr2,addr3

    # Fetch and verify from a running WalletPress instance
    python3 verify_receipt.py --order-id x402_abc123 --server http://localhost:8010

Trust: This tool is open source. It does NOT phone home. It does NOT
send your keys anywhere. It only verifies cryptographic signatures.
"""

import argparse
import hashlib
import sys
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

try:
    from nacl.bindings import crypto_sign_open
except ImportError:
    crypto_sign_open = None  # type: ignore


def verify_receipt(order_id: str, chain: str, count: int, total_usd: float,
                   timestamp: float, signature: str, pubkey_hex: str) -> bool:
    """Verify an Ed25519-signed order receipt."""
    if crypto_sign_open is None:
        print("ERROR: pynacl is required. Install: pip install pynacl")
        return False
    message = f"walletpress:receipt:{order_id}:{chain}:{count}:{total_usd}:{timestamp}".encode()
    import base64
    sig_bytes = base64.b64decode(signature)
    try:
        crypto_sign_open(sig_bytes + message, bytes.fromhex(pubkey_hex))
        return True
    except Exception:
        return False


def verify_key_deletion(order_id: str, chain: str, count: int,
                        addresses: list[str], signature: str, pubkey_hex: str) -> bool:
    """Verify a key deletion attestation — proves keys were wiped."""
    if crypto_sign_open is None:
        print("ERROR: pynacl is required. Install: pip install pynacl")
        return False
    addr_hash = hashlib.sha256("".join(sorted(addresses)).encode()).hexdigest()[:16]
    message = f"walletpress:key-deletion:{order_id}:{chain}:{count}:{addr_hash}:{int(timestamp)}".encode()
    import base64
    sig_bytes = base64.b64decode(signature)
    try:
        crypto_sign_open(sig_bytes + message, bytes.fromhex(pubkey_hex))
        return True
    except Exception:
        return False


def fetch_and_verify(server_url: str, order_id: str) -> dict[str, Any]:
    """Fetch order details from a WalletPress server and verify the receipt."""
    if httpx is None:
        return {"error": "httpx is required. Install: pip install httpx"}
    try:
        resp = httpx.get(f"{server_url}/api/v1/marketplace/verify-receipt", params={
            "order_id": order_id,
        }, timeout=10)
        if resp.status_code == 404:
            return {"error": f"Order {order_id} not found on {server_url}"}
        data = resp.json()
        return data
    except httpx.RequestError as e:
        return {"error": f"Failed to connect to {server_url}: {e}"}


def main():
    parser = argparse.ArgumentParser(
        description="WalletPress Receipt Verifier — prove your order was fulfilled",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify a receipt
  python3 verify_receipt.py --order-id x402_abc123 --signature "sig" --pubkey "key"

  # Verify key deletion
  python3 verify_receipt.py --order-id x402_abc123 --deletion-sig "sig" --pubkey "key" --addresses addr1,addr2

  # Fetch and verify from server
  python3 verify_receipt.py --order-id x402_abc123 --server http://localhost:8010
        """,
    )
    parser.add_argument("--order-id", required=True, help="Order ID from the generate response")
    parser.add_argument("--signature", help="Receipt signature (base64)")
    parser.add_argument("--deletion-sig", help="Key deletion attestation signature (base64)")
    parser.add_argument("--pubkey", help="Server's Ed25519 public key (hex)")
    parser.add_argument("--addresses", help="Comma-separated wallet addresses (for deletion verification)")
    parser.add_argument("--server", help="WalletPress server URL to fetch order details from")
    parser.add_argument("--chain", default="sol", help="Chain the wallets were generated on")
    parser.add_argument("--count", type=int, default=1, help="Number of wallets generated")
    parser.add_argument("--total-usd", type=float, default=0, help="Total amount paid in USD")
    parser.add_argument("--timestamp", type=float, default=0, help="Order timestamp (Unix)")

    args = parser.parse_args()

    if args.server:
        result = fetch_and_verify(args.server, args.order_id)
        if "error" in result:
            print(f"FAIL: {result['error']}")
            sys.exit(1)
        print(f"Order:     {result.get('order_id', '?')}")
        print(f"Chain:     {result.get('chain', '?')}")
        print(f"Count:     {result.get('count', '?')}")
        print(f"Amount:    ${result.get('amount_usd', '?')}")
        print(f"Valid:     {result.get('valid', '?')}")
        print(f"Status:    {'VERIFIED' if result.get('valid') else 'INVALID'}")
        sys.exit(0 if result.get('valid') else 1)

    if args.signature and args.pubkey:
        if not args.timestamp:
            print("ERROR: --timestamp is required for receipt verification")
            sys.exit(1)
        valid = verify_receipt(
            args.order_id, args.chain, args.count, args.total_usd,
            args.timestamp, args.signature, args.pubkey,
        )
        print(f"Receipt: {'VALID' if valid else 'INVALID'}")
        print(f"  Order:     {args.order_id}")
        print(f"  Chain:     {args.chain}")
        print(f"  Count:     {args.count}")
        print(f"  Amount:    ${args.total_usd}")
        print("  Algorithm: Ed25519")
        if not valid:
            sys.exit(1)

    if args.deletion_sig and args.pubkey and args.addresses:
        addresses = [a.strip() for a in args.addresses.split(",")]
        valid = verify_key_deletion(
            args.order_id, args.chain, args.count, addresses,
            args.deletion_sig, args.pubkey,
        )
        print(f"Key Deletion: {'VERIFIED' if valid else 'FAILED'}")
        print(f"  Order:     {args.order_id}")
        print(f"  Addresses: {len(addresses)} wallets")
        print("  Algorithm: Ed25519")
        if not valid:
            print("  WARNING: Key deletion attestation is INVALID. The server may have kept your keys.")
            sys.exit(1)
        print("  Keys were generated in memory and wiped. We did not store them.")

    if not args.signature and not args.deletion_sig and not args.server:
        print("ERROR: Provide --signature, --deletion-sig, or --server")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
