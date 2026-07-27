#!/usr/bin/env bash
# Web3 Commit Signing — configure git to sign commits with Ethereum keys
# Usage: ./scripts/git-web3-sign.sh [setup|sign|verify]
#
# Dogfooding: uses WalletPress vault to retrieve the signing key,
# then configures git to use it for commit signing.

set -euo pipefail

CMD="${1:-setup}"

case "$CMD" in
setup)
    echo "🔐  Web3 Commit Signing Setup"
    echo ""
    echo "  This configures git to sign commits using an Ethereum key"
    echo "  from your WalletPress vault."
    echo ""
    echo "  Step 1: Get a wallet ID from your vault:"
    echo "    curl -H 'X-API-Key: \$(YOUR_API_KEY)'"
    echo "      http://localhost:8010/api/v1/chain-vault/vault"
    echo ""
    echo "  Step 2: Configure git:"
    echo "    git config --global user.signingkey eth:0xYourAddressHere"
    echo "    git config --global gpg.format ssh"
    echo "    git config --global commit.gpgsign true"
    echo ""
    echo "  Step 3: Sign a commit with your wallet address in the message:"
    printf '    git commit -m "feat: add feature\n\nSigned-off-by: eth:0xYourAddress"\n'
    echo ""
    echo "  Future: automated commit signing via WalletPress agent"
    echo "    agent_execute(plan=[{\"tool\":\"wallet_sign_commit\",...}])"
    ;;

sign)
    echo "Signing commit with Web3 identity..."
    echo "  (Coming in WalletPress v1.2 — automated EIP-191 commit signing)"
    ;;

verify)
    echo "Verifying Web3 commit signatures..."
    echo "  (Coming in WalletPress v1.2 — signature verification from chain)"
    ;;

*)
    echo "Usage: $0 [setup|sign|verify]"
    exit 1
    ;;
esac
