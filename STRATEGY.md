# WalletPress — Complete Go-To-Market Strategy

## The Core Insight

**We compete on convenience, not on code.**

The code is MIT. Anyone can run it. But running 55 chains reliably
is a genuine engineering problem — not artificial scarcity. Our job
is to make the hosted version so much more convenient that $29/mo
feels like stealing.

---

## The Six Delivery Channels

### 1. WordPress Plugin (Free — the funnel)

**Hook:** 43% of the web uses WordPress. They search "crypto wallet plugin."
We're the only result that works. 3 chains free, nag bar in admin.

**Lock-in:** Once they configure wallet login, token gates, and payment
buttons on their site, switching costs are high.

**Upsell:** "Unlock 55 chains →" button in the admin bar, on every page.
The nag is polite but persistent:
```
[WalletPress] You're using Community Edition (3 of 55 chains).
Upgrade to Pro for $199 (one-time) or Hosted for $29/mo →
```

### 2. Self-Hosted (Linux) — Buy $199

**The setup flow (designed to be just painful enough):**

```
Step 1: Download the binary or Docker image
Step 2: Create /etc/walletpress/ directory
Step 3: Generate and set WP_ADMIN_KEY + WP_VAULT_PASSWORD
Step 4: Buy a license key at walletpress.cc → save to /etc/walletpress/license.key
Step 5: Configure 55 RPC endpoints (expect 2-4 hours)
   - Sign up with Infura, Alchemy, QuickNode, Helius, TronGrid, etc.
   - Create API keys for each
   - Add them to /etc/walletpress/rpc.json
Step 6: Set up SSL (certbot + nginx reverse proxy)
Step 7: Set up systemd service (included, just enable it)
Step 8: Set up backups (cron + rsync to your storage)
Step 9: Set up monitoring (uptime + health checks)
Step 10: Run `walletpress doctor` to verify everything

Total time for a senior dev: 3-5 hours.
Total time to diagnose a broken RPC at 2am: 30-60 minutes.
```

**Every pain point is a sales pitch:**
```
⚠ 43 of 55 chains have no RPC endpoint configured.
  Balance checking and transaction broadcast will fail.
  → Use Hosted ($29/mo) for zero-config RPC across all chains.
```

### 3. Hosted (walletpress.cc) — $29/mo

**Zero setup. Login with GitHub. Start generating wallets in 2 minutes.**

- All RPC pre-configured across 55 chains
- SSL, backups, updates handled
- Web dashboard at walletpress.cc/app
- Usage analytics, API keys, team management
- Priority support (email within 4 hours)

### 4. x402 API Marketplace — $0.01/wallet

**For bots and automated systems. No account, no subscription.**

Pay USDC per wallet, get keys back, we don't store them.
Pricing tiers based on volume.

### 5. Desktop App (Tauri/Electron) — Coming v2

**For non-technical users who want a native app.**

- Windows/macOS/Linux native installers (.exe, .dmg, .deb, .AppImage)
- Bundled backend — runs locally, no server needed
- Beautiful GUI for generating and managing wallets
- Offline mode — generate wallets without internet
- Same license model: free (3 chains) or Pro ($199)

### 6. Mobile PWA / React Native — Coming v2

**Generate wallets from your phone.**

- Progressive Web App (no app store required)
- Push notifications for alerts
- QR code scanner for importing keys
- Biometric auth (FaceID/TouchID)

---

## The "Doctor" Command

A CLI command that checks everything and shows an interactive report.

```bash
$ walletpress doctor

WalletPress Doctor — v1.1.0
════════════════════════════

  ✓ License:           Pro (permanent key)
  ✓ Vault encryption:  AES-256-GCM
  ✗ RPC endpoints:     12/55 configured
  ✗ SSL certificate:   Not configured
  ✓ Systemd service:   Running
  ✗ Daily backups:     Not configured
  ✓ Admin API key:     Set
  ✗ Monitoring:        Not configured
  ⚠ Upgrades:          2 releases behind (v1.1.0 available)

  Issues found: 4
  Estimated fix time: 2 hours
  → Save time with Hosted ($29/mo): all issues handled automatically
```

---

## The "walletpress.app" Web Dashboard

A hosted web application for managing wallets without WordPress.

### Features:
- **Vault:** Browse, search, export wallets. Click to copy address.
- **Generate:** Single or batch. Pick chain, count, label.
- **API Keys:** Create, revoke, monitor usage.
- **Health Dashboard:** Wallet health scores, red flags, recommendations.
- **Airdrop Tool:** Upload CSV, generate wallets, download manifest.
- **Settings:** RPC configuration, email alerts, webhooks, 2FA.
- **Billing:** Upgrade, downgrade, payment history, invoices.

### Tech stack:
- React 19 + Vite + Tailwind CSS
- Deployed on Vercel/Netlify (static, fast)
- Talks to the same backend API
- PWA: works offline, installable on phone

---

## Marketing Wins (Not Built Yet)

### Win 1: The "WalletPress vs DIY" Calculator
A page on the site that shows:
```
DIY setup cost:
  Senior dev time: 5 hours × $150/hr = $750
  RPC provider subscriptions: $50/mo
  Server hosting: $20/mo
  Ongoing maintenance: 2 hrs/month = $300/mo
  Total first year: $4,950

WalletPress Hosted: $29/mo = $348/year
WalletPress Pro (self-hosted): $199 one-time + $70/mo infra = $1,039 first year
```

### Win 2: The "WalletPress vs BitGo" Comparison
```
BitGo: $500+/mo, 40 chains, closed source, no WordPress plugin
WalletPress: $29/mo or $199, 55 chains, open source (MIT), WordPress plugin
```

### Win 3: The "Trust, But Verify" Test Vector Page
Already built at `/verify.html`. Every chain has published test vectors
showing "mnemonic X → address Y." Users verify with their own wallet.

### Win 4: The "Proof of Generation" Explorer
A public page where anyone can check a wallet's attestation.
`walletpress.cc/proof/{wallet_id}` — shows creation time, code version.

### Win 5: GitHub Sponsors / Open Source Badge
"Built with WalletPress" badge for projects that use it.
The badge links back to walletpress.cc (backlinks + SEO).

### Win 6: One-Click Deploy to Railway / Render
"Deploy WalletPress in 2 minutes" button that provisions the hosted
version with their custom domain and SSL. This IS the hosted version
with a different entry point.

---

## Revenue Model Summary

| Channel | Price | Target User | Decision |
|---------|-------|-------------|----------|
| WordPress Plugin | Free | Anyone with a WP site | "Works, upgrade later" |
| Self-Hosted License | $199 one-time | Devs who want control | "I'll manage it myself" |
| Hosted Subscription | $29/mo | Everyone else | "Just works" |
| x402 API | $0.01/wallet | Bots, automation | "No commitment, pay per use" |
| Airdrop Tool | Included in Pro | Token launches | "Came for the airdrop, stayed for the vault" |
| Health Monitoring | Included in Pro | Ops teams | "Credit Karma for wallets" |

## The Funnel

```
WordPress Plugin (free) → see "55 chains" → click upgrade
       │                              │
       ▼                              ▼
  Buy $199 license              Subscribe $29/mo
  (self-host)                   (hosted)
       │                              │
       ▼                              ▼
  walletpress doctor            walletpress.cc/app
  "fix these 4 issues"          everything works
  → consider hosted             → happy user
```
