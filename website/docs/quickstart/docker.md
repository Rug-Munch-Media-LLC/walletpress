---

title: "Quickstart with Docker"
description: "Get WalletPress running in Docker in under 2 minutes. Production-ready configuration with PostgreSQL, Redis, and persistent volumes."
keywords: [docker, quickstart, walletpress, deployment, postgresql, redis]
unlisted: false
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';


## Prerequisites

- Docker 24+ and Docker Compose v2+
- 2GB+ RAM available
- Ports 8010 (API), 5432 (PostgreSQL), 6379 (Redis) available

---

## One-Command Production Deploy

```bash
# Create project directory
mkdir walletpress && cd walletpress

# Download docker-compose
curl -L https://raw.githubusercontent.com/RugMunchMedia/walletpress/main/docker-compose.yml -o docker-compose.yml

# Generate secure vault key
export VAULT_KEY=$(openssl rand -base64 32)

# Start all services
docker compose up -d
```

That's it. WalletPress API will be available at `http://localhost:8010`.

---

## What Gets Deployed

| Service       | Image                            | Port | Purpose                      |
| ------------- | -------------------------------- | ---- | ---------------------------- |
| `walletpress` | `walletpress/walletpress:latest` | 8010 | REST API, MCP, x402          |
| `postgres`    | `postgres:16-alpine`             | 5432 | Primary database             |
| `redis`       | `redis:7-alpine`                 | 6379 | Cache, queues, rate limiting |

---

## Configuration

### Environment Variables

Create a `.env` file (or export in shell):

```bash
# Required
VAULT_KEY=                        # 32-byte base64 key (generate: openssl rand -base64 32)
DATABASE_URL=postgresql://user:pass@postgres:5432/walletpress
REDIS_URL=redis://redis:6379

# Optional
LOG_LEVEL=info                    # debug, info, warn, error
API_RATE_LIMIT=100                # requests per second per IP
MCP_ENABLED=true                  # enable MCP server
X402_ENABLED=true                 # enable x402 marketplace
WORDPRESS_PLUGIN_ENABLED=true     # enable WordPress plugin endpoints
ARWEAVE_ENABLED=true              # enable Arweave proof commits
```

### Generating VAULT_KEY

```bash
# Option 1: OpenSSL (recommended)
openssl rand -base64 32

# Option 2: Python
python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"

# Option 3: Node.js
node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"
```

**Save this key securely.** Losing it means losing access to all encrypted wallet data.

---

## Verify Installation

```bash
# Health check
curl http://localhost:8010/health
# {"status":"healthy","version":"1.0.0","services":{"database":"connected","redis":"connected","vault":"unlocked"}}

# API documentation (Swagger UI)
open http://localhost:8010/docs

# MCP endpoint (SSE)
curl -N http://localhost:8010/mcp/sse

# x402 endpoint
curl http://localhost:8010/.well-known/x402
```

---

## First Wallet Generation

```bash
# Generate a wallet for Ethereum and Solana
curl -X POST http://localhost:8010/api/v1/wallets \
  -H "Content-Type: application/json" \
  -d '{
    "chains": ["ethereum", "solana"],
    "label": "my-first-wallet",
    "derivation_path": "m/44\'/60\'/0\'/0/0"
  }'

# Response
{
  "id": "wlt_abc123...",
  "label": "my-first-wallet",
  "chains": {
    "ethereum": {
      "address": "0x742d35Cc6634C0532925a3b8D4C0532925a3b8D4",
      "derivation_path": "m/44'/60'/0'/0/0",
      "public_key": "0x04..."
    },
    "solana": {
      "address": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
      "derivation_path": "m/44'/501'/0'/0'",
      "public_key": "<solana-public-key>"
    }
  },
  "created_at": "2026-11-02T12:00:00Z",
  "arweave_proof": "https://arweave.net/abc123..."
}
```

---

## Production Hardening

### Reverse Proxy (nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name api.walletpress.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.walletpress.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.walletpress.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support for MCP SSE
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint (no auth)
    location /health {
        proxy_pass http://localhost:8010/health;
        access_log off;
    }
}
```

### Systemd Service

```ini
# /etc/systemd/system/walletpress.service
[Unit]
Description=WalletPress API
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/walletpress
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now walletpress
```

### Backup Strategy

```bash
#!/bin/bash
# /opt/walletpress/backup.sh - run via cron daily at 03:00

BACKUP_DIR="/backups/walletpress/$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"

# Database
docker exec walletpress-postgres pg_dump -U walletpress walletpress | gzip > "$BACKUP_DIR/database.sql.gz"

# Vault data (encrypted)
docker cp walletpress:/data/vault "$BACKUP_DIR/vault"

# Arweave proofs index
docker exec walletpress-postgres pg_dump -U walletpress -t arweave_proofs walletpress | gzip > "$BACKUP_DIR/arweave_proofs.sql.gz"

# Retain 30 days
find /backups/walletpress -type d -mtime +30 -exec rm -rf {} \;
```

---

## Troubleshooting

| Issue                          | Solution                                                            |
| ------------------------------ | ------------------------------------------------------------------- |
| `vault: locked`                | Check `VAULT_KEY` matches the one used to encrypt data              |
| `database: connection refused` | Ensure PostgreSQL is healthy: `docker compose logs postgres`        |
| `redis: connection refused`    | Ensure Redis is healthy: `docker compose logs redis`                |
| Port 8010 in use               | Change port in `docker-compose.yml` or stop conflicting service     |
| MCP SSE not working            | Ensure nginx proxy has `proxy_http_version 1.1` and upgrade headers |

---

## Next Steps

- [API Reference →](../api/wallet-generation.md)
- [MCP Server Setup →](../mcp/overview.md)
- [WordPress Plugin →](../wordpress/installation.md)
- [Security Model →](../security/overview.md)
- [Production Deployment →](../deployment/self-hosted.md)
