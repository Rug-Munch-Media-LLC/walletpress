<?php
defined('ABSPATH') || exit;

class WalletPressAdmin {
    private WalletPress $plugin;

    private array $tabs = [];

    public function __construct(WalletPress $plugin) {
        $this->plugin = $plugin;
        add_action('admin_menu', [$this, 'add_menu']);
        add_action('admin_init', [$this, 'register_settings']);
        add_action('admin_init', [$this, 'handle_actions']);
        add_filter('plugin_action_links_' . plugin_basename(WALLETPRESS_FILE), [$this, 'action_links']);
    }

    public function action_links(array $links): array {
        $links[] = '<a href="' . admin_url('admin.php?page=walletpress-setup') . '">' . __('Setup', 'walletpress') . '</a>';
        $links[] = '<a href="' . admin_url('admin.php?page=walletpress-settings') . '">' . __('Settings', 'walletpress') . '</a>';
        return $links;
    }

    public function add_menu(): void {
        $icon = 'data:image/svg+xml;base64,' . base64_encode('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>');
        add_menu_page('WalletPress', 'WalletPress', 'manage_options', 'walletpress', [$this, 'page_dashboard'], $icon, 30);

        $pages = [
            'walletpress'         => ['Dashboard', [$this, 'page_dashboard']],
            'walletpress-setup'   => ['Setup', [$this, 'page_setup']],
            'walletpress-vault'   => ['Vault', [$this, 'page_vault']],
            'walletpress-gen'     => ['Generate', [$this, 'page_generate']],
            'walletpress-mnemonic'=> ['Mnemonic', [$this, 'page_mnemonic']],
            'walletpress-recover' => ['Recovery', [$this, 'page_recovery']],
            'walletpress-sweep'   => ['Sweep', [$this, 'page_sweep']],
            'walletpress-escrow'  => ['Escrow', [$this, 'page_escrow']],
            'walletpress-gates'   => ['Gates', [$this, 'page_gates']],
            'walletpress-payments'=> ['Payments', [$this, 'page_payments']],
            'walletpress-keys'    => ['API Keys', [$this, 'page_api_keys']],
            'walletpress-webhooks'=> ['Webhooks', [$this, 'page_webhooks']],
            'walletpress-alerts'  => ['Alerts', [$this, 'page_alerts']],
            'walletpress-audit'   => ['Audit', [$this, 'page_audit']],
            'walletpress-plugins' => ['Plugins', [$this, 'page_plugins']],
            'walletpress-settings'=> ['Settings', [$this, 'page_settings']],
        ];
        foreach ($pages as $slug => [$title, $cb]) {
            $parent = $slug === 'walletpress' ? null : 'walletpress';
            add_submenu_page($parent ?: 'walletpress', $title, $title, 'manage_options', $slug, $cb);
        }
    }

    public function register_settings(): void {
        $s = [
            'walletpress_api_url' => ['esc_url_raw', ''],
            'walletpress_api_key' => ['sanitize_text_field', ''],
            'walletpress_merchant_wallet' => ['sanitize_text_field', ''],
            'walletpress_merchant_chain' => ['sanitize_text_field', 'solana'],
            'walletpress_default_chain' => ['sanitize_text_field', 'solana'],
            'walletpress_auto_create_users' => ['rest_sanitize_boolean', '1'],
            'walletpress_default_role' => ['sanitize_text_field', 'subscriber'],
            'walletpress_login_enabled' => ['rest_sanitize_boolean', '1'],
            'walletpress_payments_enabled' => ['rest_sanitize_boolean', '1'],
            'walletpress_setup_complete' => ['rest_sanitize_boolean', '0'],
        ];
        foreach ($s as $k => [$cb, $default]) {
            register_setting('walletpress_settings', $k, ['sanitize_callback' => $cb, 'default' => $default]);
        }
    }

    public function handle_actions(): void {
        if (!isset($_GET['page']) || !current_user_can('manage_options')) return;
        $page = $_GET['page'];

        // Handle gate creation
        if ($page === 'walletpress-gates' && $_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['save_gate'])) {
            check_admin_referer('walletpress_save_gate');
            $gates = get_option('walletpress_gates', []);
            $gates[] = [
                'title' => sanitize_text_field($_POST['gate_title']),
                'token' => sanitize_text_field($_POST['gate_token']),
                'chain' => sanitize_text_field($_POST['gate_chain']),
                'min_amount' => floatval($_POST['gate_min_amount']),
                'created_at' => current_time('mysql'),
            ];
            update_option('walletpress_gates', $gates);
            wp_redirect(admin_url('admin.php?page=walletpress-gates&msg=created'));
            exit;
        }
        if ($page === 'walletpress-gates' && isset($_GET['action']) && $_GET['action'] === 'delete' && isset($_GET['id'])) {
            check_admin_referer('walletpress_delete_gate');
            $gates = get_option('walletpress_gates', []);
            $id = (int) $_GET['id'];
            if (isset($gates[$id])) { unset($gates[$id]); update_option('walletpress_gates', array_values($gates)); }
            wp_redirect(admin_url('admin.php?page=walletpress-gates&msg=deleted'));
            exit;
        }
    }

    private function api(): WalletPressAPI { return $this->plugin->api(); }
    private function notice(string $msg, string $type = 'success'): void {
        echo '<div class="notice notice-' . esc_attr($type) . ' is-dismissible"><p>' . esc_html($msg) . '</p></div>';
    }

    // ═══════════════════════════════════════════════════════════
    //  DASHBOARD
    // ═══════════════════════════════════════════════════════════

    public function page_dashboard(): void {
        $health = $this->api()->is_configured() ? $this->api()->health() : null;
        $stats = $this->api()->is_configured() ? $this->api()->stats() : null;
        $vault = $this->api()->is_configured() ? $this->api()->list_vault() : null;
        $wallet_count = is_array($vault) ? count($vault) - 1 : 0; // subtract _meta
        $chains = $this->api()->is_configured() ? $this->api()->list_chains() : null;
        $chain_count = is_array($chains) ? count($chains) : 0;
        $setup = get_option('walletpress_setup_complete', '0');
        ?>
        <div class="wrap walletpress-dashboard">
            <h1>WalletPress <span class="walletpress-version">v<?php echo WALLETPRESS_VERSION; ?></span>
                <?php if (!$setup): ?><a href="<?php echo admin_url('admin.php?page=walletpress-setup'); ?>" class="page-title-action"><?php esc_html_e('Run Setup', 'walletpress'); ?></a><?php endif; ?>
            </h1>
            <div class="walletpress-stats-grid">
                <div class="walletpress-stat <?php echo $health ? 'stat-ok' : 'stat-warn'; ?>">
                    <span class="stat-icon">🔌</span>
                    <span class="stat-value"><?php echo $health ? 'Connected' : ($this->api()->is_configured() ? 'Error' : 'Offline'); ?></span>
                    <span class="stat-label">Backend API</span>
                </div>
                <div class="walletpress-stat">
                    <span class="stat-icon">🏦</span>
                    <span class="stat-value"><?php echo esc_html($wallet_count); ?></span>
                    <span class="stat-label">Wallets in Vault</span>
                </div>
                <div class="walletpress-stat">
                    <span class="stat-icon">⛓️</span>
                    <span class="stat-value"><?php echo esc_html($chain_count ?: '29'); ?></span>
                    <span class="stat-label">Supported Chains</span>
                </div>
                <div class="walletpress-stat">
                    <span class="stat-icon">🔐</span>
                    <span class="stat-value"><?php echo esc_html(count(get_option('walletpress_gates', []))); ?></span>
                    <span class="stat-label">Token Gates</span>
                </div>
            </div>
            <div class="walletpress-cols">
                <div class="walletpress-col">
                    <div class="walletpress-card"><h3>Quick Actions</h3>
                        <p><a href="<?php echo admin_url('admin.php?page=walletpress-gen'); ?>" class="button">Generate Wallet</a>
                        <a href="<?php echo admin_url('admin.php?page=walletpress-vault'); ?>" class="button">Browse Vault</a>
                        <a href="<?php echo admin_url('admin.php?page=walletpress-mnemonic'); ?>" class="button">Mnemonic Converter</a></p>
                        <p><a href="<?php echo admin_url('admin.php?page=walletpress-gates'); ?>" class="button">Token Gates</a>
                        <a href="<?php echo admin_url('admin.php?page=walletpress-keys'); ?>" class="button">API Keys</a></p>
                    </div>
                    <div class="walletpress-card"><h3>Shortcodes</h3>
                        <table class="widefat striped">
                            <tr><td><code>[wallet_connect]</code></td><td>Wallet login buttons</td></tr>
                            <tr><td><code>[wallet_gate id="0"]</code></td><td>Token-gated content</td></tr>
                            <tr><td><code>[wallet_pay amount="10"]</code></td><td>Crypto payment button</td></tr>
                            <tr><td><code>[wallet_generate]</code></td><td>Wallet generator (admins)</td></tr>
                        </table>
                    </div>
                </div>
                <div class="walletpress-col">
                    <div class="walletpress-card"><h3>API Endpoints</h3>
                        <p>The backend exposes <strong>86+ REST endpoints</strong> at <code><?php echo esc_html(get_option('walletpress_api_url', '(not set)')); ?></code></p>
                        <p>OpenAPI docs at <code><?php echo esc_html(get_option('walletpress_api_url', '') . '/docs'); ?></code></p>
                        <p>All endpoints are accessible via the WP plugin admin or directly via curl/httpx.</p>
                    </div>
                    <?php if (is_array($stats)): ?>
                    <div class="walletpress-card"><h3>Vault Stats</h3>
                        <pre style="max-height:200px;overflow:auto;"><?php echo esc_html(json_encode($stats, JSON_PRETTY_PRINT)); ?></pre>
                    </div>
                    <?php endif; ?>
                </div>
            </div>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  SETUP WIZARD
    // ═══════════════════════════════════════════════════════════

    public function page_setup(): void {
        $step = isset($_GET['step']) ? (int) $_GET['step'] : 1;
        if ($_SERVER['REQUEST_METHOD'] === 'POST') {
            if ($step === 1) { update_option('walletpress_api_url', esc_url_raw($_POST['walletpress_api_url']));
                update_option('walletpress_api_key', sanitize_text_field($_POST['walletpress_api_key']));
                wp_redirect(admin_url('admin.php?page=walletpress-setup&step=2')); exit; }
            if ($step === 2) { update_option('walletpress_merchant_wallet', sanitize_text_field($_POST['walletpress_merchant_wallet']));
                update_option('walletpress_merchant_chain', sanitize_text_field($_POST['walletpress_merchant_chain']));
                wp_redirect(admin_url('admin.php?page=walletpress-setup&step=3')); exit; }
            if ($step === 3 && isset($_POST['save_gate'])) {
                check_admin_referer('walletpress_save_gate');
                $gates = get_option('walletpress_gates', []);
                $gates[] = ['title' => sanitize_text_field($_POST['gate_title']), 'token' => sanitize_text_field($_POST['gate_token']), 'chain' => sanitize_text_field($_POST['gate_chain']), 'min_amount' => floatval($_POST['gate_min_amount']), 'created_at' => current_time('mysql')];
                update_option('walletpress_gates', $gates);
                update_option('walletpress_setup_complete', '1');
                wp_redirect(admin_url('admin.php?page=walletpress-setup&step=4')); exit;
            }
        }
        ?>
        <div class="wrap walletpress-setup">
            <h1>WalletPress Setup Wizard</h1>
            <div class="walletpress-steps">
                <div class="step <?php echo $step >= 1 ? 'active' : ''; ?>">API Connection</div>
                <div class="step <?php echo $step >= 2 ? 'active' : ''; ?>">Merchant Wallet</div>
                <div class="step <?php echo $step >= 3 ? 'active' : ''; ?>">Token Gate</div>
                <div class="step <?php echo $step >= 4 ? 'active' : ''; ?>">Done</div>
            </div>
            <?php if ($step === 1): ?>
                <form method="post" class="walletpress-card">
                    <h2>Connect Your Backend API</h2>
                    <p>Enter your WalletPress backend API URL and key.</p>
                    <table class="form-table">
                        <tr><th><label for="api_url">API URL</label></th><td><input type="url" id="api_url" name="walletpress_api_url" value="<?php echo esc_attr(get_option('walletpress_api_url', '')); ?>" class="regular-text" placeholder="https://api.yourdomain.com" required></td></tr>
                        <tr><th><label for="api_key">API Key</label></th><td><input type="password" id="api_key" name="walletpress_api_key" value="<?php echo esc_attr(get_option('walletpress_api_key', '') ? '********' : ''); ?>" class="regular-text" placeholder="wp_..." required></td></tr>
                    </table>
                    <?php submit_button('Test & Continue', 'primary'); ?>
                </form>
            <?php elseif ($step === 2): ?>
                <form method="post" class="walletpress-card">
                    <h2>Set Your Merchant Wallet</h2>
                    <p>Where crypto payments will be sent.</p>
                    <table class="form-table">
                        <tr><th><label for="mw">Wallet Address</label></th><td><input type="text" id="mw" name="walletpress_merchant_wallet" value="<?php echo esc_attr(get_option('walletpress_merchant_wallet', '')); ?>" class="regular-text" placeholder="SOL or ETH address" required></td></tr>
                        <tr><th><label for="mc">Chain</label></th><td><select id="mc" name="walletpress_merchant_chain"><?php foreach ($this->plugin->supported_chains() as $k => $c): ?><option value="<?php echo esc_attr($k); ?>" <?php selected(get_option('walletpress_merchant_chain', 'solana'), $k); ?>><?php echo esc_html($c['label']); ?></option><?php endforeach; ?></select></td></tr>
                    </table>
                    <?php submit_button('Continue', 'primary'); ?>
                </form>
            <?php elseif ($step === 3): ?>
                <form method="post" class="walletpress-card">
                    <h2>Create Your First Token Gate</h2>
                    <p>Restrict content to users who hold a specific token.</p>
                    <?php wp_nonce_field('walletpress_save_gate'); ?>
                    <table class="form-table">
                        <tr><th><label for="gt">Gate Name</label></th><td><input type="text" id="gt" name="gate_title" class="regular-text" placeholder="NFT Holders" required></td></tr>
                        <tr><th><label for="ga">Token Contract</label></th><td><input type="text" id="ga" name="gate_token" class="regular-text code" placeholder="Token mint/contract address" required></td></tr>
                        <tr><th><label for="gc">Chain</label></th><td><select id="gc" name="gate_chain"><?php foreach ($this->plugin->supported_chains() as $k => $c): ?><option value="<?php echo esc_attr($k); ?>"><?php echo esc_html($c['label']); ?></option><?php endforeach; ?></select></td></tr>
                        <tr><th><label for="gm">Min Amount</label></th><td><input type="number" id="gm" name="gate_min_amount" value="1" step="0.000001" min="0" class="small-text"></td></tr>
                    </table>
                    <?php submit_button('Save Gate & Finish', 'primary', 'save_gate'); ?>
                </form>
            <?php elseif ($step === 4): ?>
                <div class="walletpress-card">
                    <h2>Setup Complete</h2>
                    <p>WalletPress is ready. What's next:</p>
                    <ul>
                        <li><strong>Vault:</strong> <a href="<?php echo admin_url('admin.php?page=walletpress-gen'); ?>">Generate wallets</a> or <a href="<?php echo admin_url('admin.php?page=walletpress-vault'); ?>">browse your vault</a></li>
                        <li><strong>Gates:</strong> Add <code>[wallet_gate id="0"]</code> to any post to gate content</li>
                        <li><strong>API:</strong> Create <a href="<?php echo admin_url('admin.php?page=walletpress-keys'); ?>">API keys</a> for programmatic access</li>
                    </ul>
                    <a href="<?php echo admin_url('admin.php?page=walletpress'); ?>" class="button button-primary">Go to Dashboard</a>
                </div>
            <?php endif; ?>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  VAULT BROWSER
    // ═══════════════════════════════════════════════════════════

    public function page_vault(): void {
        $vault = $this->api()->list_vault();
        $search = isset($_GET['s']) ? sanitize_text_field($_GET['s']) : '';
        ?>
        <div class="wrap">
            <h1>Wallet Vault</h1>
            <form method="get" class="walletpress-card" style="display:flex;gap:8px;">
                <input type="hidden" name="page" value="walletpress-vault">
                <input type="text" name="s" value="<?php echo esc_attr($search); ?>" placeholder="Search by address or label..." style="flex:1;">
                <button class="button">Search</button>
                <a href="<?php echo admin_url('admin.php?page=walletpress-gen'); ?>" class="button button-primary">Generate New</a>
                <a href="<?php echo admin_url('admin.php?page=walletpress-mnemonic'); ?>" class="button">From Mnemonic</a>
            </form>
            <?php if (!is_array($vault) || empty($vault)): $this->notice('No wallets in vault. Generate one first.', 'info'); return; endif; ?>
            <table class="wp-list-table widefat fixed striped">
                <thead><tr><th>ID</th><th>Chain</th><th>Address</th><th>Label</th><th>Balance</th><th>Actions</th></tr></thead>
                <tbody>
                <?php foreach ($vault as $id => $w): if ($id === '_meta') continue;
                    $addr = $w['address'] ?? $w['public_key'] ?? '';
                    if ($search && !str_contains(strtolower($addr), strtolower($search)) && !str_contains(strtolower($w['label'] ?? ''), strtolower($search))) continue;
                ?>
                    <tr>
                        <td><code><?php echo esc_html(substr($id, 0, 8)); ?>..</code></td>
                        <td><?php echo esc_html($w['chain'] ?? $w['chain_key'] ?? ''); ?></td>
                        <td><code title="<?php echo esc_attr($addr); ?>"><?php echo esc_html(substr($addr, 0, 12) . '...' . substr($addr, -4)); ?></code></td>
                        <td><?php echo esc_html($w['label'] ?? ''); ?></td>
                        <td><?php echo esc_html($w['balance'] ?? $w['native_balance'] ?? '?'); ?></td>
                        <td>
                            <a href="<?php echo wp_nonce_url(admin_url('admin.php?page=walletpress-vault&action=view&id=' . $id), 'walletpress_view'); ?>" class="button button-small">View</a>
                            <button class="button button-small copy-addr" data-addr="<?php echo esc_attr($addr); ?>">Copy</button>
                        </td>
                    </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  GENERATE
    // ═══════════════════════════════════════════════════════════

    public function page_generate(): void {
        $chains = $this->api()->list_chains();
        ?>
        <div class="wrap">
            <h1>Generate Wallets</h1>
            <div class="walletpress-cols">
                <div class="walletpress-col">
                    <div class="walletpress-card">
                        <h2>Single Wallet</h2>
                        <form method="post" action="<?php echo admin_url('admin-post.php'); ?>">
                            <input type="hidden" name="action" value="walletpress_generate">
                            <?php wp_nonce_field('walletpress_gen'); ?>
                            <table class="form-table">
                                <tr><th>Chain</th><td><select name="chain"><?php if (is_array($chains)) foreach ($chains as $k => $c): ?><option value="<?php echo esc_attr($k); ?>"><?php echo esc_html($c['name'] ?? $k); ?></option><?php endforeach; else: foreach ($this->plugin->supported_chains() as $k => $c): ?><option value="<?php echo esc_attr($k); ?>"><?php echo esc_html($c['label']); ?></option><?php endforeach; endif; ?></select></td></tr>
                                <tr><th>Label</th><td><input type="text" name="label" class="regular-text" placeholder="e.g. My Trading Wallet"></td></tr>
                            </table>
                            <?php submit_button('Generate Wallet', 'primary'); ?>
                        </form>
                    </div>
                    <div class="walletpress-card">
                        <h2>Batch Generate</h2>
                        <form method="post" action="<?php echo admin_url('admin-post.php'); ?>">
                            <input type="hidden" name="action" value="walletpress_generate_batch">
                            <?php wp_nonce_field('walletpress_gen'); ?>
                            <table class="form-table">
                                <tr><th>Chains (comma-separated)</th><td><input type="text" name="chains" class="regular-text" placeholder="solana,ethereum,base" value="solana,ethereum,base,polygon,bsc"></td></tr>
                                <tr><th>Label Prefix</th><td><input type="text" name="label_prefix" class="regular-text" placeholder="batch-2026"></td></tr>
                            </table>
                            <?php submit_button('Generate Batch', 'primary'); ?>
                        </form>
                    </div>
                </div>
                <div class="walletpress-col">
                    <div class="walletpress-card">
                        <h2>Generate All Chains</h2>
                        <p>Generate a wallet for every supported chain (55).</p>
                        <form method="post" action="<?php echo admin_url('admin-post.php'); ?>">
                            <input type="hidden" name="action" value="walletpress_generate_all">
                            <?php wp_nonce_field('walletpress_gen'); ?>
                            <table class="form-table">
                                <tr><th>Label Prefix</th><td><input type="text" name="label_prefix" class="regular-text" placeholder="full-suite"></td></tr>
                            </table>
                            <?php submit_button('Generate All Chains', 'primary'); ?>
                        </form>
                    </div>
                    <div class="walletpress-card">
                        <h2>Import Existing Wallet</h2>
                        <form method="post" action="<?php echo admin_url('admin-post.php'); ?>">
                            <input type="hidden" name="action" value="walletpress_import">
                            <?php wp_nonce_field('walletpress_gen'); ?>
                            <table class="form-table">
                                <tr><th>Chain</th><td><select name="chain"><?php if (is_array($chains)) foreach ($chains as $k => $c): ?><option value="<?php echo esc_attr($k); ?>"><?php echo esc_html($c['name'] ?? $k); ?></option><?php endforeach; endif; ?></select></td></tr>
                                <tr><th>Private Key</th><td><input type="password" name="private_key" class="regular-text" placeholder="Enter private key"></td></tr>
                                <tr><th>Label</th><td><input type="text" name="label" class="regular-text" placeholder="Imported wallet"></td></tr>
                            </table>
                            <?php submit_button('Import', 'primary'); ?>
                        </form>
                    </div>
                </div>
            </div>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  MNEMONIC CONVERTER
    // ═══════════════════════════════════════════════════════════

    public function page_mnemonic(): void {
        ?>
        <div class="wrap">
            <h1>Mnemonic → Multi-Chain Converter</h1>
            <div class="walletpress-card">
                <p>Enter a BIP39 mnemonic phrase to derive addresses for all 55 supported chains. Your phrase never leaves your browser — it's sent directly to your self-hosted backend.</p>
                <form method="post">
                    <table class="form-table">
                        <tr><th><label for="mnemonic">Mnemonic Phrase</label></th><td><textarea id="mnemonic" name="mnemonic" rows="3" class="large-text code" placeholder="word1 word2 word3 ... word12" required></textarea></td></tr>
                        <tr><th><label for="passphrase">Passphrase (optional)</label></th><td><input type="text" id="passphrase" name="passphrase" class="regular-text"></td></tr>
                    </table>
                    <?php submit_button('Derive All Addresses', 'primary'); ?>
                </form>
            </div>
            <?php if ($_SERVER['REQUEST_METHOD'] === 'POST' && !empty($_POST['mnemonic'])):
                $result = $this->api()->from_mnemonic(sanitize_text_field($_POST['mnemonic']), sanitize_text_field($_POST['passphrase']));
                if ($result): ?>
                <div class="walletpress-card">
                    <h2>Results</h2>
                    <table class="wp-list-table widefat fixed striped">
                        <thead><tr><th>Chain</th><th>Address</th><th>Private Key</th></tr></thead>
                        <tbody>
                        <?php $wallets = $result['wallets'] ?? $result['result'] ?? $result; foreach ($wallets as $chain => $data): if (!is_array($data)) continue; ?>
                            <tr><td><strong><?php echo esc_html($chain); ?></strong></td>
                                <td><code><?php echo esc_html($data['address'] ?? $data['public_key'] ?? ''); ?></code></td>
                                <td><code><?php echo esc_html(substr($data['private_key'] ?? $data['wif'] ?? '', 0, 16) . '...'); ?></code></td></tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
                <?php else: $this->notice('Failed to convert mnemonic. Check your API connection.', 'error'); endif; endif; ?>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  RECOVERY
    // ═══════════════════════════════════════════════════════════

    public function page_recovery(): void {
        ?>
        <div class="wrap">
            <h1>Wallet Recovery</h1>
            <div class="walletpress-card">
                <p>Recover wallets from partial mnemonics, corrupted seeds, or lost keys. The recovery tool tries multiple BIP39 word combinations.</p>
                <p class="description">This is resource-intensive on large partial phrases. Run during low-traffic periods.</p>
                <form method="post">
                    <table class="form-table">
                        <tr><th><label for="partial">Partial Mnemonic</label></th><td><textarea id="partial" name="partial_mnemonic" rows="3" class="large-text code" placeholder="Enter known words, use ? for unknown: abandon ? ? lunar ? city vanish party uncle ? pudding" required></textarea></td></tr>
                        <tr><th>Chain</th><td><select name="chain"><?php foreach ($this->plugin->supported_chains() as $k => $c): ?><option value="<?php echo esc_attr($k); ?>"><?php echo esc_html($c['label']); ?></option><?php endforeach; ?></select></td></tr>
                    </table>
                    <?php submit_button('Attempt Recovery', 'primary'); ?>
                </form>
            </div>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  SWEEP
    // ═══════════════════════════════════════════════════════════

    public function page_sweep(): void {
        $vault = $this->api()->list_vault();
        ?>
        <div class="wrap">
            <h1>Dust Sweep & Rotate</h1>
            <div class="walletpress-cols">
                <div class="walletpress-col">
                    <div class="walletpress-card">
                        <h2>Rotate + Sweep</h2>
                        <p>Generate a new wallet key and sweep all funds from the old wallet to the new one.</p>
                        <form method="post">
                            <table class="form-table">
                                <tr><th>Source Wallet</th><td><select name="wallet_id"><?php if (is_array($vault)) foreach ($vault as $id => $w): if ($id === '_meta') continue; ?><option value="<?php echo esc_attr($id); ?>"><?php echo esc_html(($w['chain'] ?? '?') . ' - ' . substr($w['address'] ?? $id, 0, 12)); ?></option><?php endforeach; endif; ?></select></td></tr>
                                <tr><th>Destination Address</th><td><input type="text" name="to_address" class="regular-text code" placeholder="Target wallet address" required></td></tr>
                            </table>
                            <?php submit_button('Rotate & Sweep', 'primary'); ?>
                        </form>
                    </div>
                </div>
                <div class="walletpress-col">
                    <div class="walletpress-card">
                        <h2>Simple Sweep</h2>
                        <p>Sweep funds from a vault wallet to an external address (no key rotation).</p>
                        <form method="post">
                            <table class="form-table">
                                <tr><th>From Wallet</th><td><select name="from_wallet_id"><?php if (is_array($vault)) foreach ($vault as $id => $w): if ($id === '_meta') continue; ?><option value="<?php echo esc_attr($id); ?>"><?php echo esc_html(($w['chain'] ?? '?') . ' - ' . substr($w['address'] ?? $id, 0, 12)); ?></option><?php endforeach; endif; ?></select></td></tr>
                                <tr><th>To Address</th><td><input type="text" name="to_address" class="regular-text code" placeholder="External address" required></td></tr>
                            </table>
                            <?php submit_button('Sweep', 'primary'); ?>
                        </form>
                    </div>
                </div>
            </div>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  ESCROW
    // ═══════════════════════════════════════════════════════════

    public function page_escrow(): void {
        ?>
        <div class="wrap">
            <h1>Pay-to-Release Escrow</h1>
            <div class="walletpress-card">
                <p>Create time-locked escrow wallets. Funds are released when conditions are met.</p>
                <form method="post">
                    <table class="form-table">
                        <tr><th>Deposit Address</th><td><input type="text" name="deposit_address" class="regular-text code" placeholder="Wallet address receiving deposit" required></td></tr>
                        <tr><th>Amount (USD)</th><td><input type="number" name="amount" step="0.01" class="small-text" required></td></tr>
                        <tr><th>Platform</th><td><select name="platform"><option value="solana">Solana</option><option value="ethereum">Ethereum</option></select></td></tr>
                        <tr><th>Conditions (JSON)</th><td><textarea name="conditions" rows="4" class="large-text code" placeholder='{"release_after": "2026-12-31", "approved_by": ["wallet1", "wallet2"]}'></textarea></td></tr>
                    </table>
                    <?php submit_button('Create Escrow', 'primary'); ?>
                </form>
            </div>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  TOKEN GATES
    // ═══════════════════════════════════════════════════════════

    public function page_gates(): void {
        if (isset($_GET['msg'])) $this->notice($_GET['msg'] === 'created' ? 'Gate created.' : 'Gate deleted.');
        $gates = get_option('walletpress_gates', []);
        ?>
        <div class="wrap">
            <h1>Token Gates</h1>
            <table class="wp-list-table widefat fixed striped">
                <thead><tr><th>Name</th><th>Token</th><th>Chain</th><th>Min</th><th>Shortcode</th><th>Actions</th></tr></thead>
                <tbody>
                <?php if (empty($gates)): ?><tr><td colspan="6">No gates yet. Create one below.</td></tr>
                <?php else: foreach ($gates as $id => $g): ?>
                    <tr><td><?php echo esc_html($g['title']); ?></td><td><code><?php echo esc_html(substr($g['token'], 0, 16) . '...'); ?></code></td><td><?php echo esc_html($g['chain']); ?></td><td><?php echo esc_html($g['min_amount']); ?></td>
                        <td><code>[wallet_gate id="<?php echo esc_attr($id); ?>"]</code> <button class="button button-small copy-shortcode" data-code='[wallet_gate id="<?php echo esc_attr($id); ?>"]'>Copy</button></td>
                        <td><a href="<?php echo wp_nonce_url(admin_url('admin.php?page=walletpress-gates&action=delete&id=' . $id), 'walletpress_delete_gate'); ?>" class="button button-small">Delete</a></td></tr>
                <?php endforeach; endif; ?>
                </tbody>
            </table>
            <form method="post" class="walletpress-card" style="margin-top:20px;">
                <h2>New Gate</h2>
                <?php wp_nonce_field('walletpress_save_gate'); ?>
                <table class="form-table">
                    <tr><th>Gate Name</th><td><input type="text" name="gate_title" class="regular-text" placeholder="e.g. NFT Holders Only" required></td></tr>
                    <tr><th>Token Contract</th><td><input type="text" name="gate_token" class="regular-text code" placeholder="So11111111111111111111111111111111111111112" required></td></tr>
                    <tr><th>Chain</th><td><select name="gate_chain"><?php foreach ($this->plugin->supported_chains() as $k => $c): ?><option value="<?php echo esc_attr($k); ?>"><?php echo esc_html($c['label']); ?></option><?php endforeach; ?></select></td></tr>
                    <tr><th>Min Amount</th><td><input type="number" name="gate_min_amount" value="1" step="0.000001" min="0" class="small-text"></td></tr>
                </table>
                <?php submit_button('Create Gate', 'primary', 'save_gate'); ?>
            </form>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  PAYMENTS
    // ═══════════════════════════════════════════════════════════

    public function page_payments(): void {
        $payments = get_option('walletpress_payments_log', []);
        $total = array_sum(array_column($payments, 'amount_usd'));
        ?>
        <div class="wrap">
            <h1>Payments</h1>
            <div class="walletpress-stats-grid" style="margin-bottom:20px;">
                <div class="walletpress-stat"><span class="stat-value">$<?php echo number_format($total, 2); ?></span><span class="stat-label">Total Revenue</span></div>
                <div class="walletpress-stat"><span class="stat-value"><?php echo count($payments); ?></span><span class="stat-label">Transactions</span></div>
                <div class="walletpress-stat"><span class="stat-value"><?php echo count(array_filter($payments, fn($p) => ($p['status'] ?? '') === 'confirmed')); ?></span><span class="stat-label">Confirmed</span></div>
            </div>
            <table class="wp-list-table widefat fixed striped">
                <thead><tr><th>Date</th><th>From</th><th>Amount</th><th>Token</th><th>Status</th><th>TX</th></tr></thead>
                <tbody>
                <?php if (empty($payments)): ?><tr><td colspan="6">No payments yet.</td></tr>
                <?php else: foreach (array_reverse($payments) as $p): ?>
                    <tr><td><?php echo esc_html($p['created_at'] ?? ''); ?></td><td><code><?php echo esc_html(substr($p['from'] ?? '', 0, 8) . '...'); ?></code></td><td>$<?php echo number_format($p['amount_usd'] ?? 0, 2); ?></td><td><?php echo esc_html($p['token'] ?? 'SOL'); ?></td><td><span class="walletpress-badge badge-<?php echo esc_attr($p['status'] ?? 'pending'); ?>"><?php echo esc_html($p['status'] ?? 'pending'); ?></span></td><td><code><?php echo esc_html(substr($p['tx_hash'] ?? '', 0, 12) . '...'); ?></code></td></tr>
                <?php endforeach; endif; ?>
                </tbody>
            </table>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  API KEYS
    // ═══════════════════════════════════════════════════════════

    public function page_api_keys(): void {
        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['create_key'])) {
            check_admin_referer('walletpress_key');
            $result = $this->api()->create_api_key(sanitize_text_field($_POST['key_label']), array_map('sanitize_text_field', $_POST['key_scopes'] ?? []));
            if ($result && isset($result['api_key'])): $this->notice("Key created: {$result['api_key']} — save this now, it won't be shown again."); endif;
        }
        $keys = $this->api()->list_api_keys();
        ?>
        <div class="wrap">
            <h1>API Keys</h1>
            <form method="post" class="walletpress-card">
                <?php wp_nonce_field('walletpress_key'); ?>
                <h2>Create New Key</h2>
                <table class="form-table">
                    <tr><th>Label</th><td><input type="text" name="key_label" class="regular-text" placeholder="e.g. Production" required></td></tr>
                    <tr><th>Scopes</th><td><label><input type="checkbox" name="key_scopes[]" value="vault.read" checked> vault.read</label><br>
                        <label><input type="checkbox" name="key_scopes[]" value="vault.write"> vault.write</label><br>
                        <label><input type="checkbox" name="key_scopes[]" value="generate"> generate</label><br>
                        <label><input type="checkbox" name="key_scopes[]" value="admin"> admin</label><br>
                        <label><input type="checkbox" name="key_scopes[]" value="webhook.manage"> webhook.manage</label></td></tr>
                </table>
                <?php submit_button('Generate Key', 'primary', 'create_key'); ?>
            </form>
            <?php if (is_array($keys) && !empty($keys)): ?>
            <table class="wp-list-table widefat fixed striped">
                <thead><tr><th>Label</th><th>Key</th><th>Scopes</th><th>Created</th><th>Actions</th></tr></thead>
                <tbody>
                <?php foreach ($keys as $id => $k): ?>
                    <tr><td><?php echo esc_html($k['label'] ?? ''); ?></td><td><code><?php echo esc_html(substr($k['api_key'] ?? $id, 0, 16) . '...'); ?></code></td><td><?php echo esc_html(implode(', ', $k['scopes'] ?? [])); ?></td><td><?php echo esc_html($k['created_at'] ?? ''); ?></td><td><a href="<?php echo wp_nonce_url(admin_url('admin.php?page=walletpress-keys&action=revoke&id=' . $id), 'walletpress_key'); ?>" class="button button-small">Revoke</a></td></tr>
                <?php endforeach; ?>
                </tbody>
            </table>
            <?php endif; ?>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  WEBHOOKS
    // ═══════════════════════════════════════════════════════════

    public function page_webhooks(): void {
        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['create_webhook'])) {
            check_admin_referer('walletpress_webhook');
            $result = $this->api()->create_webhook(esc_url_raw($_POST['webhook_url']), array_map('sanitize_text_field', $_POST['webhook_events'] ?? []), sanitize_text_field($_POST['webhook_secret']));
            if ($result) $this->notice('Webhook created.');
        }
        $webhooks = $this->api()->list_webhooks();
        ?>
        <div class="wrap">
            <h1>Webhooks</h1>
            <form method="post" class="walletpress-card">
                <?php wp_nonce_field('walletpress_webhook'); ?>
                <h2>New Webhook</h2>
                <table class="form-table">
                    <tr><th>URL</th><td><input type="url" name="webhook_url" class="regular-text" placeholder="https://hooks.example.com/events" required></td></tr>
                    <tr><th>Secret</th><td><input type="text" name="webhook_secret" class="regular-text" placeholder="Shared secret for HMAC verification"></td></tr>
                    <tr><th>Events</th><td><label><input type="checkbox" name="webhook_events[]" value="wallet.generated" checked> wallet.generated</label><br>
                        <label><input type="checkbox" name="webhook_events[]" value="payment.received"> payment.received</label><br>
                        <label><input type="checkbox" name="webhook_events[]" value="gate.accessed"> gate.accessed</label><br>
                        <label><input type="checkbox" name="webhook_events[]" value="alert.triggered"> alert.triggered</label></td></tr>
                </table>
                <?php submit_button('Create Webhook', 'primary', 'create_webhook'); ?>
            </form>
            <?php if (is_array($webhooks) && !empty($webhooks)): ?>
            <table class="wp-list-table widefat fixed striped">
                <thead><tr><th>URL</th><th>Events</th><th>Created</th><th>Actions</th></tr></thead>
                <tbody>
                <?php foreach ($webhooks as $id => $w): ?>
                    <tr><td><code><?php echo esc_html($w['url'] ?? ''); ?></code></td><td><?php echo esc_html(implode(', ', $w['events'] ?? [])); ?></td><td><?php echo esc_html($w['created_at'] ?? ''); ?></td><td><a href="<?php echo wp_nonce_url(admin_url('admin.php?page=walletpress-webhooks&action=delete&id=' . $id), 'walletpress_webhook'); ?>" class="button button-small">Delete</a></td></tr>
                <?php endforeach; ?>
                </tbody>
            </table>
            <?php endif; ?>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  ALERTS
    // ═══════════════════════════════════════════════════════════

    public function page_alerts(): void {
        ?>
        <div class="wrap">
            <h1>Balance Alerts</h1>
            <div class="walletpress-card">
                <p>Get notified when wallet balances change or when specific on-chain events occur.</p>
                <form method="post">
                    <table class="form-table">
                        <tr><th>Wallet Address</th><td><input type="text" name="alert_address" class="regular-text code" placeholder="Address to monitor" required></td></tr>
                        <tr><th>Chain</th><td><select name="alert_chain"><?php foreach ($this->plugin->supported_chains() as $k => $c): ?><option value="<?php echo esc_attr($k); ?>"><?php echo esc_html($c['label']); ?></option><?php endforeach; ?></select></td></tr>
                        <tr><th>Trigger</th><td><select name="alert_type"><option value="balance_change">Balance Change</option><option value="incoming_tx">Incoming TX</option><option value="outgoing_tx">Outgoing TX</option><option value="token_movement">Token Movement</option></select></td></tr>
                        <tr><th>Notification</th><td><select name="alert_channel"><option value="email">Email</option><option value="webhook">Webhook</option><option value="telegram">Telegram</option></select></td></tr>
                    </table>
                    <?php submit_button('Create Alert', 'primary'); ?>
                </form>
            </div>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  AUDIT LOG
    // ═══════════════════════════════════════════════════════════

    public function page_audit(): void {
        $audit = $this->api()->audit_trail(100);
        ?>
        <div class="wrap">
            <h1>Audit Trail</h1>
            <?php if (!is_array($audit) || empty($audit)): $this->notice('No audit entries yet.', 'info'); return; endif; ?>
            <table class="wp-list-table widefat fixed striped">
                <thead><tr><th>Timestamp</th><th>Action</th><th>Wallet</th><th>Details</th></tr></thead>
                <tbody>
                <?php foreach ($audit as $entry): ?>
                    <tr><td><?php echo esc_html($entry['timestamp'] ?? $entry['time'] ?? ''); ?></td>
                        <td><code><?php echo esc_html($entry['action'] ?? $entry['event'] ?? ''); ?></code></td>
                        <td><code><?php echo esc_html(isset($entry['wallet_id']) ? substr($entry['wallet_id'], 0, 12) : '-'); ?></code></td>
                        <td><?php echo esc_html(is_string($entry['details'] ?? '') ? $entry['details'] : wp_json_encode($entry['details'] ?? [])); ?></td></tr>
                <?php endforeach; ?>
                </tbody>
            </table>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  PLUGINS
    // ═══════════════════════════════════════════════════════════

    public function page_plugins(): void {
        ?>
        <div class="wrap">
            <h1>Plugin System</h1>
            <p>WalletPress supports event-driven plugins that hook into wallet lifecycle events.</p>
            <div class="walletpress-cols">
                <div class="walletpress-col">
                    <div class="walletpress-card">
                        <h3>Available Events</h3>
                        <ul>
                            <li><code>before_generate</code> — Before wallet generation</li>
                            <li><code>after_generate</code> — After wallet generated</li>
                            <li><code>before_import</code> — Before wallet import</li>
                            <li><code>after_import</code> — After wallet imported</li>
                            <li><code>before_rotate</code> — Before key rotation</li>
                            <li><code>after_rotate</code> — After key rotated</li>
                            <li><code>before_sweep</code> — Before fund sweep</li>
                            <li><code>after_sweep</code> — After fund sweep</li>
                            <li><code>vault_change</code> — Any vault modification</li>
                        </ul>
                        <p class="description">Plugins are Python files dropped in the backend's <code>/app/plugins/</code> directory. They receive event data and can transform, log, or reject operations.</p>
                    </div>
                </div>
                <div class="walletpress-col">
                    <div class="walletpress-card">
                        <h3>Create a Plugin</h3>
                        <pre># /app/plugins/my_plugin.py
from app.wallet_plugins import register_hook

def on_generate(context):
    log = context.get("logger")
    wallet = context.get("wallet", {})
    log.info(f"Generated {wallet.get('chain')} wallet")
    return context  # or modify it

register_hook("after_generate", on_generate)</pre>
                        <p>See <code>wallet_plugins.py</code> in the backend for the full API.</p>
                    </div>
                </div>
            </div>
        </div>
        <?php
    }

    // ═══════════════════════════════════════════════════════════
    //  SETTINGS
    // ═══════════════════════════════════════════════════════════

    public function page_settings(): void {
        ?>
        <div class="wrap">
            <h1>WalletPress Settings</h1>
            <form method="post" action="options.php">
                <?php settings_fields('walletpress_settings'); ?>
                <div class="walletpress-card">
                    <h2>API Connection</h2>
                    <table class="form-table">
                        <tr><th><label for="wau">Backend API URL</label></th><td><input type="url" id="wau" name="walletpress_api_url" value="<?php echo esc_attr(get_option('walletpress_api_url', '')); ?>" class="regular-text" placeholder="https://api.yourdomain.com"></td></tr>
                        <tr><th><label for="wak">API Key</label></th><td><input type="password" id="wak" name="walletpress_api_key" value="<?php echo esc_attr(get_option('walletpress_api_key', '') ? '********' : ''); ?>" class="regular-text"></td></tr>
                    </table>
                </div>
                <div class="walletpress-card">
                    <h2>Merchant Wallet</h2>
                    <table class="form-table">
                        <tr><th><label for="mw2">Wallet Address</label></th><td><input type="text" id="mw2" name="walletpress_merchant_wallet" value="<?php echo esc_attr(get_option('walletpress_merchant_wallet', '')); ?>" class="regular-text code"></td></tr>
                        <tr><th><label for="mc2">Chain</label></th><td><select id="mc2" name="walletpress_merchant_chain"><?php foreach ($this->plugin->supported_chains() as $k => $c): ?><option value="<?php echo esc_attr($k); ?>" <?php selected(get_option('walletpress_merchant_chain', 'solana'), $k); ?>><?php echo esc_html($c['label']); ?></option><?php endforeach; ?></select></td></tr>
                    </table>
                </div>
                <div class="walletpress-card">
                    <h2>Features</h2>
                    <table class="form-table">
                        <tr><th>Wallet Login</th><td><label><input type="checkbox" name="walletpress_login_enabled" value="1" <?php checked('1', get_option('walletpress_login_enabled', '1')); ?>> Enable wallet-based login</label></td></tr>
                        <tr><th>Crypto Payments</th><td><label><input type="checkbox" name="walletpress_payments_enabled" value="1" <?php checked('1', get_option('walletpress_payments_enabled', '1')); ?>> Enable crypto payments</label></td></tr>
                        <tr><th><label for="dc">Default Chain</label></th><td><select id="dc" name="walletpress_default_chain"><?php foreach ($this->plugin->supported_chains() as $k => $c): ?><option value="<?php echo esc_attr($k); ?>" <?php selected(get_option('walletpress_default_chain', 'solana'), $k); ?>><?php echo esc_html($c['label']); ?></option><?php endforeach; ?></select></td></tr>
                    </table>
                </div>
                <div class="walletpress-card">
                    <h2>User Settings</h2>
                    <table class="form-table">
                        <tr><th>Auto-Create Users</th><td><label><input type="checkbox" name="walletpress_auto_create_users" value="1" <?php checked('1', get_option('walletpress_auto_create_users', '1')); ?>> Create WP user on first wallet login</label></td></tr>
                        <tr><th><label for="dr">Default Role</label></th><td><select id="dr" name="walletpress_default_role"><?php foreach (wp_roles()->get_names() as $k => $v): ?><option value="<?php echo esc_attr($k); ?>" <?php selected(get_option('walletpress_default_role', 'subscriber'), $k); ?>><?php echo esc_html($v); ?></option><?php endforeach; ?></select></td></tr>
                    </table>
                </div>
                <?php submit_button('Save Settings'); ?>
            </form>
        </div>
        <?php
    }
}
