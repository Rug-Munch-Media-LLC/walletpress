<?php
defined('ABSPATH') || exit;

class WalletPress {
    private array $modules = [];
    private ?WalletPressAPI $api = null;

    /**
     * Encrypt a value using WordPress salt as the key.
     *
     * P2-18 fix: Was AES-256-CBC without authentication (malleable, vulnerable
     * to padding-oracle / bit-flipping attacks). Now AES-256-GCM with the
     * 16-byte auth tag appended to the IV field. Format:
     *   base64( iv (12B) || ciphertext || tag (16B) )
     * On legacy decrypt() (CBC), auto-detects and decodes the old format
     * so existing encrypted values still work after an update.
     */
    public static function encrypt(string $plaintext): string {
        if ($plaintext === '') return '';
        $key = defined('LOGGED_IN_KEY') ? LOGGED_IN_KEY : wp_salt('logged_in');
        // Derive a 32-byte key from the salt (it may be shorter than 32 chars)
        $key = hash('sha256', $key, true);
        $iv = openssl_random_pseudo_bytes(12);
        $tag = '';
        $cipher = openssl_encrypt(
            $plaintext,
            'aes-256-gcm',
            $key,
            OPENSSL_RAW_DATA,
            $iv,
            $tag,
            '',
            16
        );
        // Format: base64(iv (12) || ciphertext || tag (16))
        return base64_encode($iv . $cipher . $tag);
    }

    /** Decrypt a value encrypted by encrypt(). Supports legacy CBC format. */
    public static function decrypt(string $ciphertext): string {
        if ($ciphertext === '') return '';
        $key = defined('LOGGED_IN_KEY') ? LOGGED_IN_KEY : wp_salt('logged_in');
        $data = base64_decode($ciphertext, true);
        if ($data === false || strlen($data) < 16) return '';

        // Auto-detect format. GCM: 12B IV + N ciphertext + 16B tag = at least 28B.
        // CBC legacy: 16B IV + N ciphertext. Heuristic: try GCM first if
        // (len - 12 - 16) >= 0; otherwise legacy CBC.
        $key = hash('sha256', $key, true);
        if (strlen($data) >= 28) {
            // Try GCM first
            $iv = substr($data, 0, 12);
            $tag = substr($data, -16);
            $cipher = substr($data, 12, -16);
            $plain = openssl_decrypt($cipher, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag, '');
            if ($plain !== false) return $plain;
            // Fall through to CBC attempt
        }
        // Legacy CBC: 16B IV + ciphertext
        $iv = substr($data, 0, 16);
        $cipher = substr($data, 16);
        return openssl_decrypt($cipher, 'aes-256-cbc', $key, OPENSSL_RAW_DATA, $iv) ?: '';
    }

    public function init(): void {
        add_action('init', [$this, 'load_textdomain']);
        add_action('init', [$this, 'register_shortcodes']);
        add_filter('pre_update_option_walletpress_api_key', [__CLASS__, 'encrypt'], 10, 1);
        add_filter('option_walletpress_api_key', [__CLASS__, 'decrypt'], 10, 1);
        add_action('wp_enqueue_scripts', [$this, 'enqueue_frontend']);
        add_action('admin_enqueue_scripts', [$this, 'enqueue_admin']);
        add_action('rest_api_init', [$this, 'register_routes']);
        add_filter('script_loader_tag', [$this, 'add_module_scripts'], 10, 3);

        $this->api = new WalletPressAPI(
            get_option('walletpress_api_url', ''),
            get_option('walletpress_api_key', '')
        );

        $this->modules = [
            'admin'    => new WalletPressAdmin($this),
            'auth'     => new WalletPressAuth($this),
            'gate'     => new WalletPressGate($this),
            'payments' => new WalletPressPayments($this),
        ];

        do_action('walletpress_init', $this);
    }

    public function api(): WalletPressAPI { return $this->api; }
    public function module(string $name): ?object { return $this->modules[$name] ?? null; }

    public function load_textdomain(): void {
        load_plugin_textdomain('walletpress', false, dirname(plugin_basename(WALLETPRESS_FILE)) . '/languages');
    }

    public function register_shortcodes(): void {
        add_shortcode('wallet_connect', [WalletPressAuth::class, 'render_connect_button']);
        add_shortcode('wallet_gate', [WalletPressGate::class, 'render_gate']);
        add_shortcode('wallet_pay', [WalletPressPayments::class, 'render_pay_button']);
        add_shortcode('wallet_profile', [$this, 'render_profile']);
        add_shortcode('wallet_generate', [$this, 'render_generate_shortcode']);
    }

    public function render_generate_shortcode(): string {
        if (!current_user_can('manage_options')) return '';
        ob_start(); ?>
        <div class="walletpress-generate-shortcode">
            <form class="wp-generate-form">
                <select name="chain"><?php foreach ($this->supported_chains() as $k => $c): ?>
                    <option value="<?php echo esc_attr($k); ?>"><?php echo esc_html($c['label']); ?></option>
                <?php endforeach; ?></select>
                <input type="text" name="label" placeholder="Label (optional)">
                <button type="submit" class="walletpress-btn walletpress-btn-pay">Generate</button>
            </form>
            <pre class="wp-gen-result" style="display:none;"></pre>
        </div>
        <?php
        return ob_get_clean();
    }

    public function register_routes(): void {
        $c = 'WalletPressAuth';
        $g = 'WalletPressGate';
        $p = 'WalletPressPayments';

        register_rest_route('walletpress/v1', '/auth/nonce', ['methods' => 'GET', 'callback' => [$c, 'rest_nonce'], 'permission_callback' => '__return_true']);
        register_rest_route('walletpress/v1', '/auth/verify', ['methods' => 'POST', 'callback' => [$c, 'rest_verify'], 'permission_callback' => '__return_true']);
        register_rest_route('walletpress/v1', '/auth/me', ['methods' => 'GET', 'callback' => [$c, 'rest_me'], 'permission_callback' => '__return_true']);
        register_rest_route('walletpress/v1', '/auth/balance', ['methods' => 'GET', 'callback' => [$c, 'rest_balance'], 'permission_callback' => '__return_true']);

        register_rest_route('walletpress/v1', '/generate', ['methods' => 'POST', 'callback' => [$this, 'rest_generate'], 'permission_callback' => function() { return current_user_can('manage_options'); }]);
        register_rest_route('walletpress/v1', '/vault', ['methods' => 'GET', 'callback' => [$this, 'rest_vault'], 'permission_callback' => function() { return current_user_can('manage_options'); }]);
        register_rest_route('walletpress/v1', '/verify-ownership', ['methods' => 'POST', 'callback' => [$g, 'rest_verify_ownership'], 'permission_callback' => '__return_true']);

        register_rest_route('walletpress/v1', '/payments/create', ['methods' => 'POST', 'callback' => [$p, 'rest_create_payment'], 'permission_callback' => '__return_true']);
        register_rest_route('walletpress/v1', '/payments/verify', ['methods' => 'POST', 'callback' => [$p, 'rest_verify_payment'], 'permission_callback' => '__return_true']);
    }

    public function rest_generate(WP_REST_Request $req): WP_REST_Response {
        $result = $this->api->generate_wallet(sanitize_text_field($req->get_param('chain')), sanitize_text_field($req->get_param('label')));
        return new WP_REST_Response($result ?: ['error' => 'Generation failed'], $result ? 200 : 502);
    }

    public function rest_vault(): WP_REST_Response {
        $vault = $this->api->list_vault();
        return new WP_REST_Response($vault ?: ['error' => 'Failed to fetch vault'], $vault ? 200 : 502);
    }

    public function enqueue_frontend(): void {
        wp_enqueue_script('walletpress', WALLETPRESS_URL . 'assets/js/walletpress.js', [], WALLETPRESS_VERSION, true);
        wp_enqueue_style('walletpress', WALLETPRESS_URL . 'assets/css/walletpress.css', [], WALLETPRESS_VERSION);
        $user = wp_get_current_user();
        wp_localize_script('walletpress', 'walletpress', [
            'rest' => esc_url_raw(rest_url('walletpress/v1')),
            'nonce' => wp_create_nonce('wp_rest'),
            'api_url' => get_option('walletpress_api_url', ''),
            'user' => $user->ID ? ['id' => $user->ID, 'display_name' => $user->display_name, 'wallet' => get_user_meta($user->ID, 'walletpress_address', true) ?: null] : null,
            'chains' => $this->supported_chains(),
        ]);
    }

    public function enqueue_admin(string $hook): void {
        if (str_contains($hook, 'walletpress')) {
            wp_enqueue_style('walletpress-admin', WALLETPRESS_URL . 'assets/css/walletpress.css', [], WALLETPRESS_VERSION);
            wp_enqueue_script('walletpress-admin', WALLETPRESS_URL . 'assets/js/walletpress-admin.js', [], WALLETPRESS_VERSION, true);
            wp_localize_script('walletpress-admin', 'walletpress_admin', [
                'nonce' => wp_create_nonce('walletpress_admin'),
                'ajax' => admin_url('admin-ajax.php'),
            ]);
        }
    }

    public function add_module_scripts(string $tag, string $handle, string $src): string {
        return ($handle === 'walletpress') ? str_replace('<script', '<script type="module"', $tag) : $tag;
    }

    public function supported_chains(): array {
        // Maps plugin-friendly names to backend chain keys.
        // Only chains the backend actually supports (verified in tests/test_address_vectors.py).
        // See ADDRESS_GENERATION.md for the full chain truth table.
        return [
            'btc'       => ['label' => 'Bitcoin',        'icon' => 'btc', 'wallet' => '',         'backend' => 'btc'],
            'btc-segwit'=> ['label' => 'Bitcoin SegWit',  'icon' => 'btc', 'wallet' => '',         'backend' => 'btc-segwit'],
            'eth'       => ['label' => 'Ethereum',       'icon' => 'eth', 'wallet' => 'metamask','backend' => 'eth'],
            'base'      => ['label' => 'Base',           'icon' => 'base','wallet' => 'metamask','backend' => 'base'],
            'polygon'   => ['label' => 'Polygon',        'icon' => 'matic','wallet'=> 'metamask','backend' => 'polygon'],
            'arbitrum'  => ['label' => 'Arbitrum',       'icon' => 'arb', 'wallet' => 'metamask','backend' => 'arbitrum'],
            'optimism'  => ['label' => 'Optimism',       'icon' => 'op',  'wallet' => 'metamask','backend' => 'optimism'],
            'avalanche' => ['label' => 'Avalanche',      'icon' => 'avax','wallet' => 'metamask','backend' => 'avalanche'],
            'bsc'       => ['label' => 'BNB Chain',      'icon' => 'bnb', 'wallet' => 'metamask','backend' => 'bsc'],
            'fantom'    => ['label' => 'Fantom',         'icon' => 'ftm', 'wallet' => 'metamask','backend' => 'fantom'],
            'gnosis'    => ['label' => 'Gnosis',         'icon' => 'xdai','wallet' => 'metamask','backend' => 'gnosis'],
            'celo'      => ['label' => 'Celo',           'icon' => 'celo','wallet' => 'metamask','backend' => 'celo'],
            'scroll'    => ['label' => 'Scroll',         'icon' => 'scr', 'wallet' => 'metamask','backend' => 'scroll'],
            'zksync'    => ['label' => 'zkSync Era',     'icon' => 'zk',  'wallet' => 'metamask','backend' => 'zksync'],
            'blast'     => ['label' => 'Blast',          'icon' => 'blast','wallet'=> 'metamask','backend' => 'blast'],
            'mantle'    => ['label' => 'Mantle',         'icon' => 'mnt', 'wallet' => 'metamask','backend' => 'mantle'],
            'linea'     => ['label' => 'Linea',          'icon' => 'linea','wallet'=> 'metamask','backend' => 'linea'],
            'metis'     => ['label' => 'Metis',          'icon' => 'metis','wallet'=> 'metamask','backend' => 'metis'],
            'opbnb'     => ['label' => 'opBNB',          'icon' => 'bnb', 'wallet' => 'metamask','backend' => 'opbnb'],
            'core'      => ['label' => 'Core Chain',     'icon' => 'core','wallet' => 'metamask','backend' => 'core'],
            'frax'      => ['label' => 'Fraxchain',      'icon' => 'frax','wallet' => 'metamask','backend' => 'frax'],
            'kava'      => ['label' => 'Kava',           'icon' => 'kava','wallet' => 'metamask','backend' => 'kava'],
            'moonbeam'  => ['label' => 'Moonbeam',       'icon' => 'glmr','wallet' => 'metamask','backend' => 'moonbeam'],
            'cronos'    => ['label' => 'Cronos',         'icon' => 'cro', 'wallet' => 'metamask','backend' => 'cronos'],
            'aurora'    => ['label' => 'Aurora',         'icon' => 'aurora','wallet'=> 'metamask','backend' => 'aurora'],
            'harmony'   => ['label' => 'Harmony',        'icon' => 'one', 'wallet' => 'metamask','backend' => 'harmony'],
            'boba'      => ['label' => 'Boba Network',   'icon' => 'boba','wallet' => 'metamask','backend' => 'boba'],
            'evmos'     => ['label' => 'Evmos',          'icon' => 'evmos','wallet'=> 'metamask','backend' => 'evmos'],
            'sol'       => ['label' => 'Solana',         'icon' => 'sol', 'wallet' => 'phantom', 'backend' => 'sol'],
            'trx'       => ['label' => 'TRON',           'icon' => 'trx', 'wallet' => '',         'backend' => 'trx'],
            'doge'      => ['label' => 'Dogecoin',       'icon' => 'doge','wallet' => '',         'backend' => 'doge'],
            'ltc'       => ['label' => 'Litecoin',       'icon' => 'ltc', 'wallet' => '',         'backend' => 'ltc'],
            'bch'       => ['label' => 'Bitcoin Cash',   'icon' => 'bch', 'wallet' => '',         'backend' => 'bch'],
            'dash'      => ['label' => 'Dash',           'icon' => 'dash','wallet' => '',         'backend' => 'dash'],
            'zec'       => ['label' => 'Zcash',          'icon' => 'zec', 'wallet' => '',         'backend' => 'zec'],
            'atom'      => ['label' => 'Cosmos Hub',     'icon' => 'atom','wallet' => '',         'backend' => 'atom'],
            'osmo'      => ['label' => 'Osmosis',        'icon' => 'osmo','wallet' => '',         'backend' => 'osmo'],
            'inj'       => ['label' => 'Injective',      'icon' => 'inj', 'wallet' => '',         'backend' => 'inj'],
            'algo'      => ['label' => 'Algorand',       'icon' => 'algo','wallet' => '',         'backend' => 'algo'],
            'xlm'       => ['label' => 'Stellar',        'icon' => 'xlm', 'wallet' => '',         'backend' => 'xlm'],
            'xrp'       => ['label' => 'XRP',            'icon' => 'xrp', 'wallet' => '',         'backend' => 'xrp'],
            'dot'       => ['label' => 'Polkadot',       'icon' => 'dot', 'wallet' => '',         'backend' => 'dot'],
            'ksm'       => ['label' => 'Kusama',         'icon' => 'ksm', 'wallet' => '',         'backend' => 'ksm'],
            'ada'       => ['label' => 'Cardano',        'icon' => 'ada', 'wallet' => '',         'backend' => 'ada'],
            'xmr'       => ['label' => 'Monero',         'icon' => 'xmr', 'wallet' => '',         'backend' => 'xmr'],
            'xtz'       => ['label' => 'Tezos',          'icon' => 'xtz', 'wallet' => '',         'backend' => 'xtz'],
            'fil'       => ['label' => 'Filecoin',       'icon' => 'fil', 'wallet' => '',         'backend' => 'fil'],
            'near'      => ['label' => 'NEAR',           'icon' => 'near','wallet' => '',         'backend' => 'near'],
            'sui'       => ['label' => 'Sui',            'icon' => 'sui', 'wallet' => '',         'backend' => 'sui'],
            'apt'       => ['label' => 'Aptos',          'icon' => 'apt', 'wallet' => '',         'backend' => 'apt'],
            'ton'       => ['label' => 'TON',            'icon' => 'ton', 'wallet' => '',         'backend' => 'ton'],
        ];
    }

    public function render_profile(): string {
        if (!is_user_logged_in()) return do_shortcode('[wallet_connect]');
        $user = wp_get_current_user();
        $wallet = get_user_meta($user->ID, 'walletpress_address', true);
        ob_start(); ?>
        <div class="walletpress-profile">
            <h3><?php esc_html_e('Wallet Profile', 'walletpress'); ?></h3>
            <p><strong><?php esc_html_e('User:', 'walletpress'); ?></strong> <?php echo esc_html($user->display_name); ?></p>
            <?php if ($wallet): ?>
                <p><strong><?php esc_html_e('Wallet:', 'walletpress'); ?></strong> <code><?php echo esc_html(substr($wallet, 0, 6) . '...' . substr($wallet, -4)); ?></code></p>
                <button class="walletpress-disconnect button"><?php esc_html_e('Disconnect Wallet', 'walletpress'); ?></button>
            <?php else: echo do_shortcode('[wallet_connect]'); endif; ?>
        </div>
        <?php return ob_get_clean();
    }
}
