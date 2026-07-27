# DEPLOYMENT.md — WalletPress

> How to deploy. Build, push, restart, rollback.

## Architecture
- Container: Docker
- Image registry: local/private
- Orchestration: docker-compose
- Reverse proxy: nginx
- Auto-deploy: git webhook → deploy script

## Deploy

### Automatic (CI/CD)
On merge to `main`:
1. Git webhook fires
2. Deploy host pulls latest commit
3. Rebuilds Docker image
4. Stops old container, starts new
5. Runs health check
6. Rolls back on failure

### Manual
```bash
# On the deploy host
cd /path/to/walletpress
git pull origin main
docker build -t walletpress:latest .
docker stop walletpress && docker rm walletpress
docker run -d --name walletpress --restart unless-stopped \
  --network host -p 8010:8010 \
  -e WP_ADMIN_KEY=your-admin-key \
  -e WP_VAULT_PASSWORD=your-vault-password \
  walletpress:latest
```

## Health Check
```bash
curl -fsS http://localhost:8010/health
```

## Rollback
```bash
# On the deploy host
cd /path/to/walletpress
git log --oneline -5   # find last good commit
git checkout <commit-hash>
docker build -t walletpress:latest .
docker restart walletpress
```

## Logs
```bash
docker logs walletpress --tail 100 -f
```

## Monitoring
- Prometheus: `/metrics` endpoint
- Grafana: dashboards
- Loki: log aggregation

## Secrets
All secrets are passed via environment variables or a `.env` file:

- `WP_ADMIN_KEY` — admin API key
- `WP_VAULT_PASSWORD` — vault encryption password
- `WP_PAYMENT_ADDRESS` — x402 marketplace payment address

Never commit secrets to git.

## Firewall
- Public ports: nginx
- Internal: localhost only, behind nginx

## Backup
- Code: git repository (source of truth)
- Data: database backup (daily)
- Keys: vault password stored securely offline
