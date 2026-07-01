#!/bin/sh
# Entry runs as root. Chown data dir then exec CMD as walletpress (per Dockerfile USER directive).
set -e

mkdir -p /data
# chown needs to be done as root (current user)
chown -R walletpress:walletpress /data
chmod 755 /data

# Print info
echo "[walletpress] data dir ready: /data"
echo "[walletpress] starting: $@"

# Exec the CMD — runs as walletpress (Dockerfile USER directive)
exec "$@"
