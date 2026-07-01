# DEPLOYMENT.md — WalletPress

> How to deploy. Build, push, restart, rollback.

## Architecture
- Container: Docker
- Image registry: local (Talos)
- Orchestration: docker-compose on Talos
- Reverse proxy: nginx on Talos
- Auto-deploy: forgejo webhook → Talos deploy script

## Deploy

### Automatic (CI/CD)
On merge to `main`:
1. forgejo webhook fires
2. Talos deploy script pulls latest commit
3. Rebuilds Docker image
4. Stops old container, starts new
5. Runs health check
6. Rolls back on failure

### Manual
```bash
ssh netcup
cd /srv/walletpress
git pull origin main
docker build -t walletpress:latest .
docker stop walletpress
docker rm walletpress
docker run -d --name walletpress --restart unless-stopped --network host -p 8010:8010 walletpress:latest
```

## Health Check
```bash
curl -fsS http://localhost:8010/health
```

## Rollback
```bash
ssh netcup
cd /srv/walletpress
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
- Grafana: dashboards in fleet-infra
- Loki: log aggregation

## Secrets
All secrets in gopass:
- `rmi/walletpress/admin_key`
- `rmi/walletpress/db_password`
- _see AGENTS.md for full list_

Loaded via docker `--env-file` or systemd `EnvironmentFile`.

## Firewall
- Public: 80, 443 (nginx)
- Internal: 8010 (localhost only, behind nginx)
- Tailscale: 8010 for admin access

## Backup
- Code: forgejo (source of truth) + Hydra bare mirror (daily 04:00)
- Data: DB snapshot to R2 (daily)
- Config: gopass
