---

title: "WordPress Plugin — Token Gating, Crypto Payments, Wallet Login"
description: "Free tier: 3 chains. Token gating, crypto payments, wallet-based login for any WordPress site. The funnel into the ecosystem — give it away, then scale up. BSL 1.1 licensed."
keywords: [wordpress plugin, token gating, crypto payments, wallet login, web3 wordpress, bip39]
unlisted: false
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';


**Early Access**

**The WordPress plugin is your funnel into WalletPress.** Free tier gives 3 chains, token gating, crypto payments, and wallet-based login. Upgrade to Pro for all 55 chains and x402 marketplace.

---

## Quick Install

```bash
# Via WP Admin
1. Download walletpress-plugin.zip from walletpress.cc
2. WP Admin → Plugins → Add New → Upload Plugin
3. Activate → Settings → WalletPress → Enter API key
4. Done. Shortcodes work immediately.
```

```bash
# Via WP-CLI
wp plugin install https://walletpress.cc/downloads/walletpress-plugin-latest.zip --activate
wp walletpress config set api_key wp_live_EXAMPLE
```

---

## What It Does

### Token Gating

Restrict content, pages, products, or entire sites to token holders.

```php
// Shortcode
[walletpress_gate token="0x0000000000000000000000000000000000000000" network="ethereum" amount="1"]
  <p>This content is for token holders only.</p>
[/walletpress_gate]

// PHP
if (walletpress_user_has_token('0x742d35...', 'ethereum', 1)) {
    // Show gated content
}
```

**Supports:** ERC-20, ERC-721, ERC-1155, SPL tokens, native coins.

### Crypto Payments

Accept USDC, USDT, ETH, SOL, and 50+ tokens directly on your site.

```php
// Shortcode — payment button
[walletpress_pay amount="29.99" currency="USDC" chain="base" success_url="/thank-you"]
[walletpress_pay amount="0.01" currency="ETH" chain="ethereum" metadata='{"order_id": 12345}']

// PHP — custom integration
$payment = walletpress_create_payment([
    'amount' => 29.99,
    'currency' => 'USDC',
    'chain' => 'base',
    'success_url' => '/thank-you',
    'metadata' => ['order_id' => 12345]
]);
// Returns: payment_url, invoice_id, expires_at
```

**Settlement:** USDC on Base/Solana/Arbitrum → your wallet in seconds. No Stripe, no 2.9% + $0.30.

### Wallet Login (Web3 Auth)

Replace email/password with wallet signatures.

```php
// Shortcode — login button
[walletpress_login redirect="/dashboard"]

// PHP — custom flow
$nonce = walletpress_get_nonce();  // Returns SIWE message
// User signs in their wallet (MetaMask, Phantom, etc.)
$user = walletpress_verify_signature($signature, $nonce);
// Returns: WP_User object, logged in
```

**Standards:** SIWE (EIP-4361) for EVM, Solana Wallet Adapter for Solana.

---

## Free vs Pro

*See pricing table below.*

---

## Installation

### Requirements

- WordPress 6.0+
- PHP 8.1+
- HTTPS (required for wallet connections)
- `openssl` PHP extension
- `json` PHP extension

### API Key Setup

1. Get API key from [walletpress.cc/dashboard](https://walletpress.cc/dashboard)
2. WP Admin → WalletPress → Settings → API Key
3. Paste key → Save
4. Test connection → "Connected to WalletPress Pro"

---

## Shortcodes Reference

### Token Gating

```php
// Basic
[walletpress_gate token="0x..." network="ethereum"]

// With amount
[walletpress_gate token="0x..." network="ethereum" amount="10"]

// NFT gating
[walletpress_gate token="0x..." network="ethereum" standard="erc721" token_id="123"]

// Custom message
[walletpress_gate token="0x..." network="ethereum"]
  <div class="premium-content">Members only!</div>
[/walletpress_gate]

// Redirect if not eligible
[walletpress_gate token="0x..." network="ethereum" redirect="/upgrade"]
```

### Payments

```php
// Simple
[walletpress_pay amount="9.99" currency="USDC" chain="base"]

// With metadata
[walletpress_pay amount="49.00" currency="USDC" chain="base"
  success_url="/thank-you?order={order_id}"
  metadata='{"product_id": "course-101"}']

// Subscription (Pro only)
[walletpress_subscribe amount="29.00" currency="USDC" chain="base"
  interval="month" trial_days="7"]
```

### Wallet Login

```php
// Button
[walletpress_login text="Connect Wallet" redirect="/dashboard"]

// With custom networks
[walletpress_login networks="ethereum,polygon,base,solana"]

// Profile display
[walletpress_profile show_address="true" show_balance="true" show_ens="true"]
```

---

## WooCommerce Integration (Pro)

```php
// Enable in WP Admin → WalletPress → WooCommerce
// Adds payment gateway: "WalletPress Crypto"

// Supported:
// - One-time payments
// - Subscriptions (WooCommerce Subscriptions)
// - Pre-orders
// - Deposits
// - Refunds (auto via x402)
```

**Hooks:**

```php
add_action('walletpress_payment_completed', function($payment) {
    // $payment: ['invoice_id', 'amount', 'currency', 'chain', 'tx_hash', 'order_id']
    wc_create_order([...]);
});

add_action('walletpress_payment_failed', function($error) {
    // Log, notify admin, etc.
});
```

---

## Elementor & Gutenberg Blocks (Pro)

**Elementor Widgets:**
- WalletPress Token Gate
- WalletPress Pay Button
- WalletPress Login
- WalletPress Profile

**Gutenberg Blocks:**
- `/walletpress-gate`
- `/walletpress-pay`
- `/walletpress-login`
- `/walletpress-profile`

Drag, drop, configure — no code needed.

---

## Webhooks (Pro)

Configure in WP Admin → WalletPress → Webhooks:

| Event                   | Payload                                                    |
| ----------------------- | ---------------------------------------------------------- |
| `payment.completed`     | `{invoice_id, amount, currency, chain, tx_hash, order_id}` |
| `payment.failed`        | `{invoice_id, error, attempt}`                             |
| `payment.refunded`      | `{invoice_id, refund_tx_hash}`                             |
| `user.wallet_connected` | `{user_id, address, chain}`                                |
| `user.token_verified`   | `{user_id, token, network, balance}`                       |
| `gate.access_granted`   | `{user_id, post_id, token}`                                |
| `gate.access_denied`    | `{user_id, post_id, token, reason}`                        |

**Security:** All webhooks signed with `X-WalletPress-Signature` (HMAC-SHA256).

```php
// Verify in your endpoint
$signature = $_SERVER['HTTP_X_WALLETPRESS_SIGNATURE'];
$payload = file_get_contents('php://input');
$expected = hash_hmac('sha256', $payload, $WEBHOOK_SECRET);
if (!hash_equals($expected, $signature)) {
    http_response_code(401);
    exit;
}
```

---

## Template Overrides

Copy templates to your theme:

```
your-theme/
└── walletpress/
    ├── gate.php           // Token gate content wrapper
    ├── pay-button.php     // Payment button
    ├── login-form.php     // Login form
    ├── profile.php        // User profile
    └── email/
        ├── payment-received.php
        ├── payment-failed.php
        └── wallet-connected.php
```

---

## Multisite Support

```php
// Network activate → each site gets own settings
// Network admin can set default API key
// Per-site override in site's WP Admin
```

---

## Performance

- **Caching:** Token balances cached 5 min (configurable)
- **Ajax:** All wallet interactions async
- **Assets:** ~15KB CSS + JS (deferred, no jQuery)
- **Database:** Custom tables, indexed for speed

---

## Troubleshooting

| Issue                         | Fix                                                       |
| ----------------------------- | --------------------------------------------------------- |
| "Invalid API key"             | Check key in WalletPress dashboard, regenerate if needed  |
| "Wallet not connecting"       | Ensure HTTPS, check browser console for CORS errors       |
| "Payment stuck pending"       | Check webhook delivery in WP Admin → WalletPress → Logs   |
| "Token gate not working"      | Clear cache, verify token address + network match exactly |
| "WooCommerce gateway missing" | Ensure Pro license active, flush rewrite rules            |

---

## Next

- [WordPress Installation →](wordpress/installation.md)
- [WordPress Configuration →](wordpress/configuration.md)
- [Shortcodes Deep Dive →](wordpress/shortcodes.md)
- [WooCommerce Setup →](wordpress/woocommerce.md)
- [Webhooks →](wordpress/webhooks.md)
