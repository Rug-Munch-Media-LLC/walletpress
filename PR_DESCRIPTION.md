## Fixes walletpress backend deployment blockers

The walletpress backend was unable to start due to 4 issues. This PR fixes all of them.

### #1 — requirements.lock incomplete
**Problem:** `requirements.lock` was missing deps. The Dockerfile used `requirements.lock` for `pip install`, so the runtime couldn't import `python-multipart` (FastAPI Form data), `mcp` (MCP SDK), and various chain-specific deps.

**Fix:** Switched Dockerfile to use `requirements.txt` (which has all loose pins) instead of the incomplete lock. Also added `python-multipart>=0.0.9` and `mcp>=1.25.0` to `requirements.txt`.

### #2 — main.py wrong import name (AuditTrail)
**Problem:** `from core.audit import AuditTrail` — class doesn't exist; only `AuditLog` does.

**Fix:** Changed import and usage to `AuditLog`.

### #3 — main.py wrong import path (PersistentStore)
**Problem:** `from routers.chain_vault import _PersistentStore` — neither `_PersistentStore` nor `_persistent_store` exists in `chain_vault.py`. The actual class is `PersistentStore` (no underscore prefix) in `routers/_persistent_store.py`.

**Fix:** Changed import to `from routers._persistent_store import PersistentStore`.

### #4 — DB volume permissions
**Problem:** `/data/walletpress/walletpress.db` couldn't be opened (`unable to open database file`). The mounted volume had wrong ownership and the previous Dockerfile chown'd `/data` to walletpress user, but only at build time — the runtime mount overwrote this.

**Fix:** Added `entrypoint.sh` that runs as root on container start, ensures `/data` exists, chowns to `walletpress:walletpress`, then `exec`s the CMD. Also fixed Dockerfile ordering (COPY entrypoint + chmod must happen before USER directive).

### Verification
After all fixes:
```
{"status":"ok","version":"1.1.0","service":"walletpress","checks":{"vault":"ok","key_store":"ok","proof":"ok","webhooks":"ok"}}
```
- Container: `walletpress-backend` Up (healthy)
- API: 112 endpoints exposed at `/backend/*` via nginx
- Tailscale access works (no auth)
- Direct IP requires basic auth (401 without)

### Test plan
```bash
# Tailnet
curl https://walletpress.rugmunch.io/backend/health
curl https://walletpress.rugmunch.io/backend/docs

# Direct IP (needs creds)
curl -u crmuncher:<password> https://[INTERNAL_IP]/backend/health
```

Closes the 4 blockers documented in fleet-infra/ADMIN-ACCESS.md.
