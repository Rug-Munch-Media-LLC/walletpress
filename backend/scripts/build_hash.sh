#!/bin/bash
# WalletPress Build Verification Hash
# =====================================
# Generates a SHA-256 hash of the entire source tree, excluding
# git history, virtual environments, and build artifacts.
#
# This hash PROVES which version of the code was used to build
# the Docker image. Compare with the published hash on our site.
#
# Usage:
#   ./scripts/build_hash.sh          # Print hash
#   ./scripts/build_hash.sh --write  # Write to build.hash
#   ./scripts/build_hash.sh --check  # Verify against build.hash

set -euo pipefail

HASH_FILE="build.hash"
EXCLUDE="-not -path './.git/*' -not -path './venv/*' -not -path '*/__pycache__/*' -not -name '*.pyc' -not -name '.env' -not -name 'htmlcov' -not -path './build.hash'"

case "${1:-}" in
  --write)
    find . -type f $EXCLUDE | sort | xargs sha256sum | sha256sum | cut -d' ' -f1 > "$HASH_FILE"
    echo "Build hash written to $HASH_FILE: $(cat $HASH_FILE)"
    ;;
  --check)
    if [ ! -f "$HASH_FILE" ]; then
      echo "Error: $HASH_FILE not found. Run with --write first."
      exit 1
    fi
    EXPECTED=$(cat "$HASH_FILE")
    ACTUAL=$(find . -type f $EXCLUDE | sort | xargs sha256sum | sha256sum | cut -d' ' -f1)
    if [ "$EXPECTED" = "$ACTUAL" ]; then
      echo "✓ Build hash MATCHES — code has not been modified"
      exit 0
    else
      echo "✗ Build hash MISMATCH — code has changed since hash was written"
      echo "  Expected: $EXPECTED"
      echo "  Actual:   $ACTUAL"
      exit 1
    fi
    ;;
  *)
    find . -type f $EXCLUDE | sort | xargs sha256sum | sha256sum | cut -d' ' -f1
    ;;
esac
