<?php
defined('ABSPATH') || exit;

class WalletPressAPI {
    private string $base_url;
    private string $api_key;
    private int $timeout;

    public function __construct(string $base_url = '', string $api_key = '', int $timeout = 30) {
        $this->base_url = untrailingslashit($base_url);
        $this->api_key  = $api_key;
        $this->timeout  = $timeout;
    }

    public function is_configured(): bool {
        return !empty($this->base_url) && !empty($this->api_key);
    }

    private function url(string $path): string {
        return $this->base_url . $path;
    }

    private function headers(): array {
        $h = ['Content-Type' => 'application/json'];
        if (!empty($this->api_key)) {
            $h['X-API-Key'] = $this->api_key;
            $h['Authorization'] = 'Bearer ' . $this->api_key;
        }
        return $h;
    }

    private function call(string $method, string $path, ?array $body = null): ?array {
        $args = ['timeout' => $this->timeout, 'headers' => $this->headers()];
        if ($body !== null) {
            $args['body'] = wp_json_encode($body);
        }
        $response = $method === 'GET' ? wp_remote_get($this->url($path), $args) : wp_remote_post($this->url($path), $args);
        if (is_wp_error($response)) {
            $this->log('API error: ' . $response->get_error_message());
            return null;
        }
        $code = wp_remote_retrieve_response_code($response);
        $data = json_decode(wp_remote_retrieve_body($response), true);
        if ($code < 200 || $code >= 300) {
            $this->log("API {$code}: " . wp_remote_retrieve_body($response));
            return null;
        }
        return $data;
    }

    private function log(string $msg): void {
        if (defined('WP_DEBUG') && WP_DEBUG) {
            error_log("[WalletPress] {$msg}");
        }
    }

    // ─── Health ────────────────────────────────────────────
    public function health(): ?array { return $this->call('GET', '/health'); }

    // ─── Chain Vault (wallet factory) ──────────────────────
    private const CV = '/api/v1/chain-vault';

    public function list_chains(): ?array { return $this->call('GET', self::CV . '/chains'); }
    public function stats(): ?array { return $this->call('GET', self::CV . '/stats'); }
    public function health_score(string $wallet_id): ?array { return $this->call('GET', self::CV . "/health-score/{$wallet_id}"); }
    public function healthz(): ?array { return $this->call('GET', self::CV . '/healthz'); }

    // --- Generation ---
    public function generate_wallet(string $chain, string $label = '', array $tags = []): ?array {
        return $this->call('POST', self::CV . '/generate', ['chain' => $chain, 'label' => $label, 'tags' => $tags]);
    }
    public function generate_batch(array $chains, string $label_prefix = ''): ?array {
        return $this->call('POST', self::CV . '/generate/batch', ['chains' => $chains, 'label_prefix' => $label_prefix]);
    }
    public function generate_all(): ?array { return $this->call('POST', self::CV . '/generate/batch', ['chains' => []]); }
    public function from_mnemonic(string $mnemonic, string $passphrase = ''): ?array {
        return $this->call('POST', self::CV . '/from-mnemonic', ['mnemonic' => $mnemonic, 'passphrase' => $passphrase]);
    }

    // --- Vault ---
    public function list_vault(): ?array { return $this->call('GET', self::CV . '/vault'); }
    public function get_wallet(string $wallet_id): ?array { return $this->call('GET', self::CV . "/vault/{$wallet_id}"); }
    public function rotate_wallet(string $wallet_id): ?array {
        return $this->call('POST', self::CV . '/rotate', ['wallet_id' => $wallet_id]);
    }
    public function export_wallets(string $format = 'json', array $ids = []): ?array {
        return $this->call('POST', self::CV . '/export', ['format' => $format, 'ids' => $ids]);
    }
    public function rotate_sweep(string $wallet_id, string $to_address): ?array {
        return $this->call('POST', self::CV . '/rotate-sweep', ['wallet_id' => $wallet_id, 'to_address' => $to_address]);
    }
    public function distribute_wallets(array $distributions): ?array {
        return $this->call('POST', self::CV . '/distribute', ['distributions' => $distributions]);
    }

    // --- Wallet Tree ---
    public function wallet_tree(): ?array { return $this->call('GET', self::CV . '/tree'); }
    public function cluster_generate(string $chain, int $count = 10): ?array {
        return $this->call('POST', self::CV . '/cluster', ['chain' => $chain, 'count' => $count]);
    }

    // --- Escrow ---
    public function create_escrow(string $platform, string $deposit_address, array $conditions, float $amount): ?array {
        return $this->call('POST', self::CV . '/escrow', [
            'platform' => $platform, 'deposit_address' => $deposit_address,
            'conditions' => $conditions, 'amount' => $amount,
        ]);
    }
    public function release_escrow(string $escrow_id): ?array {
        return $this->call('POST', self::CV . '/escrow/release', ['escrow_id' => $escrow_id]);
    }

    // --- Mnemonic convert (full /derive endpoint) ---
    public function derive_address(string $mnemonic, string $chain, string $path = ''): ?array {
        return $this->call('POST', self::CV . '/derive-address', ['mnemonic' => $mnemonic, 'chain' => $chain, 'path' => $path]);
    }

    // --- Import ---
    public function import_wallet(string $chain, string $private_key, string $label = ''): ?array {
        return $this->call('POST', self::CV . '/import', ['chain' => $chain, 'private_key' => $private_key, 'label' => $label]);
    }

    // --- HD Wallet ---
    public function create_hd_wallet(string $mnemonic, string $password = ''): ?array {
        return $this->call('POST', self::CV . '/hd-wallet', ['mnemonic' => $mnemonic, 'password' => $password]);
    }

    // --- Paper Wallet ---
    public function paper_wallet(string $wallet_id): ?array {
        return $this->call('GET', self::CV . "/paper-wallet/{$wallet_id}");
    }

    // --- Audit ---
    public function audit_trail(int $limit = 50): ?array {
        return $this->call('GET', self::CV . '/audit-trail', ['limit' => $limit]);
    }

    // --- Bulk Operations ---
    public function bulk_filter(array $filters): ?array {
        return $this->call('POST', self::CV . '/bulk/filter', ['filters' => $filters]);
    }
    public function bulk_delete(array $ids): ?array {
        return $this->call('POST', self::CV . '/bulk/delete', ['ids' => $ids]);
    }
    public function bulk_export(string $format = 'csv', array $ids = []): ?array {
        return $this->call('POST', self::CV . '/bulk/export', ['format' => $format, 'ids' => $ids]);
    }

    // --- Validation ---
    public function validate_address(string $chain, string $address): ?array {
        return $this->call('GET', self::CV . "/validate/{$chain}/{$address}");
    }
    public function validate_all(): ?array { return $this->call('GET', self::CV . '/validate/all'); }

    // --- Balances ---
    public function list_balances(): ?array { return $this->call('GET', self::CV . '/balances'); }
    public function balance_snapshot(): ?array { return $this->call('POST', self::CV . '/balances/snapshot'); }
    public function balance_history(int $days = 30): ?array {
        return $this->call('GET', self::CV . '/balances/history', ['days' => $days]);
    }

    // --- RPC Chains ---
    public function rpc_chains(): ?array { return $this->call('GET', self::CV . '/rpc-chains'); }

    // --- Cross-Chain Linking ---
    public function link_proof(string $source_address, string $source_chain, string $target_chain): ?array {
        return $this->call('POST', self::CV . '/link/proof', [
            'source_address' => $source_address, 'source_chain' => $source_chain, 'target_chain' => $target_chain,
        ]);
    }
    public function link_verify(string $address, string $chain, string $proof): ?array {
        return $this->call('POST', self::CV . '/link/verify', ['address' => $address, 'chain' => $chain, 'proof' => $proof]);
    }

    // --- Temporal Wallets ---
    public function temporal_create(string $chain, int $ttl_seconds, string $label = ''): ?array {
        return $this->call('POST', self::CV . '/temporal/create', ['chain' => $chain, 'ttl_seconds' => $ttl_seconds, 'label' => $label]);
    }
    public function temporal_release(string $temporal_id): ?array {
        return $this->call('POST', self::CV . '/temporal/release', ['temporal_id' => $temporal_id]);
    }
    public function temporal_list(): ?array { return $this->call('GET', self::CV . '/temporal/list'); }

    // --- Sweep ---
    public function sweep_wallet(string $from_wallet_id, string $to_address): ?array {
        return $this->call('POST', self::CV . '/sweep', ['from_wallet_id' => $from_wallet_id, 'to_address' => $to_address]);
    }

    // --- Funding Bundle ---
    public function funding_bundle(string $chain, string $wallet_id, float $amount): ?array {
        return $this->call('POST', self::CV . '/funding-bundle', ['chain' => $chain, 'wallet_id' => $wallet_id, 'amount' => $amount]);
    }

    // --- Deployer Setup ---
    public function deployer_setup(string $chain, string $wallet_id): ?array {
        return $this->call('POST', self::CV . '/deployer-setup', ['chain' => $chain, 'wallet_id' => $wallet_id]);
    }

    // --- Transaction Builder ---
    public function tx_build(string $chain, string $from, string $to, float $amount, array $opts = []): ?array {
        return $this->call('POST', self::CV . '/tx/build', array_merge(['chain' => $chain, 'from' => $from, 'to' => $to, 'amount' => $amount], $opts));
    }
    public function tx_broadcast(string $chain, string $signed_tx): ?array {
        return $this->call('POST', self::CV . '/tx/broadcast', ['chain' => $chain, 'signed_tx' => $signed_tx]);
    }

    // --- API Keys ---
    public function create_api_key(string $label, array $scopes = ['vault.read']): ?array {
        return $this->call('POST', self::CV . '/api-keys', ['label' => $label, 'scopes' => $scopes]);
    }
    public function list_api_keys(): ?array { return $this->call('GET', self::CV . '/api-keys'); }
    public function revoke_api_key(string $key_id): ?array {
        return $this->call('POST', self::CV . '/api-keys/revoke', ['key_id' => $key_id]);
    }

    // --- Alerts ---
    public function create_alert(array $config): ?array {
        return $this->call('POST', self::CV . '/alerts', $config);
    }
    public function list_alerts(): ?array { return $this->call('GET', self::CV . '/alerts'); }
    public function delete_alert(string $alert_id): ?array {
        return $this->call('POST', self::CV . '/alerts/delete', ['alert_id' => $alert_id]);
    }

    // --- Webhooks ---
    public function create_webhook(string $url, array $events = [], string $secret = ''): ?array {
        return $this->call('POST', self::CV . '/webhooks', ['url' => $url, 'events' => $events, 'secret' => $secret]);
    }
    public function list_webhooks(): ?array { return $this->call('GET', self::CV . '/webhooks'); }
    public function delete_webhook(string $webhook_id): ?array {
        return $this->call('DELETE', self::CV . "/webhooks/{$webhook_id}");
    }

    // ─── Wallet Analysis (domain/wallet) ──────────────────
    private const WA = '/api/v1/wallet';

    public function get_balance(string $address, string $chain = 'solana'): ?array {
        return $this->call('GET', self::WA . "/{$address}/balance", ['chain' => $chain]);
    }
    public function analyze_wallet(string $address, string $chain = 'solana'): ?array {
        return $this->call('GET', self::WA . "/{$address}/analyze", ['chain' => $chain]);
    }
    public function scan_wallet(string $address, string $chain = 'solana', string $tier = 'free'): ?array {
        return $this->call('POST', self::WA . '/scan', ['address' => $address, 'chain' => $chain, 'tier' => $tier]);
    }
    public function verify_signature(string $address, string $message, string $signature, string $chain = 'solana'): ?array {
        return $this->call('POST', self::WA . '/verify', ['address' => $address, 'message' => $message, 'signature' => $signature, 'chain' => $chain]);
    }
    public function get_transactions(string $address, string $chain = 'solana', int $limit = 50): ?array {
        return $this->call('GET', self::WA . "/{$address}/transactions", ['chain' => $chain, 'limit' => $limit]);
    }

    // ─── Payments ──────────────────────────────────────────
    public function create_payment(string $from, string $to, float $amount, string $token = 'SOL', string $chain = 'solana'): ?array {
        return $this->call('POST', '/api/v1/chain-vault/payments/create', [
            'wallet_id' => 'payment_' . sanitize_key($from),
            'amount_usd' => $amount,
            'chain' => $chain,
            'token' => $token,
            'description' => "Payment from {$from} to {$to}",
        ]);
    }

    public function verify_payment(string $tx_hash, string $chain = 'solana'): ?array {
        return $this->call('POST', '/api/v1/chain-vault/payments/verify', [
            'payment_id' => 'pay_verification',
            'tx_hash' => $tx_hash,
            'chain' => $chain,
        ]);
    }

    // ─── Token Ownership ───────────────────────────────────
    public function check_ownership(string $address, string $contract, string $chain = 'solana'): ?array {
        return $this->call('GET', "/api/v1/wallet-memory/labels/{$address}", ['chain' => $chain]);
    }

    // ─── Wallet Memory (clustering) ────────────────────────
    private const WM = '/api/v1/wallet-memory';

    public function cluster_wallets(array $addresses, string $method = 'behavioral'): ?array {
        return $this->call('POST', self::WM . '/cluster', ['addresses' => $addresses, 'method' => $method]);
    }
    public function resolve_entity(string $address): ?array {
        return $this->call('GET', self::WM . "/resolve/{$address}");
    }
    public function wallet_labels(string $address): ?array {
        return $this->call('GET', self::WM . "/labels/{$address}");
    }
    public function risk_score(string $address, string $chain = 'solana'): ?array {
        return $this->call('GET', self::WM . "/risk/{$address}", ['chain' => $chain]);
    }
}
