<?php
defined('ABSPATH') || exit;

class WalletPressAuth {
    private static ?WalletPress $plugin = null;

    public function __construct(WalletPress $plugin) {
        self::$plugin = $plugin;

        add_action('wp_ajax_walletpress_disconnect', [__CLASS__, 'ajax_disconnect']);
        add_action('wp_ajax_nopriv_walletpress_disconnect', [__CLASS__, 'ajax_disconnect']);
        add_filter('show_admin_bar', [__CLASS__, 'maybe_show_admin_bar'], 10, 2);
    }

    public static function render_connect_button(): string {
        if (is_user_logged_in()) {
            return '';
        }

        ob_start();
        ?>
        <div class="walletpress-connect">
            <button class="walletpress-btn walletpress-btn-metamask" data-wallet="metamask">
                <span class="walletpress-wallet-icon">🦊</span>
                <?php esc_html_e('Sign in with MetaMask', 'walletpress'); ?>
            </button>
            <button class="walletpress-btn walletpress-btn-phantom" data-wallet="phantom">
                <span class="walletpress-wallet-icon">👻</span>
                <?php esc_html_e('Sign in with Phantom', 'walletpress'); ?>
            </button>
            <button class="walletpress-btn walletpress-btn-walletconnect" data-wallet="walletconnect">
                <span class="walletpress-wallet-icon">🔗</span>
                <?php esc_html_e('WalletConnect', 'walletpress'); ?>
            </button>
            <p class="walletpress-error" style="display:none;color:#dc3232;"></p>
            <p class="walletpress-status" style="display:none;"></p>
        </div>
        <?php
        return ob_get_clean();
    }

    public static function rest_nonce(): WP_REST_Response {
        $nonce = wp_generate_password(24, false);
        $hash  = wp_hash($nonce, 'walletpress_auth');

        set_transient('walletpress_nonce_' . $hash, $nonce, 300);

        return new WP_REST_Response([
            'nonce'     => $nonce,
            'hash'      => $hash,
            'expires_in' => 300,
        ], 200);
    }

    public static function rest_verify(WP_REST_Request $request): WP_REST_Response {
        $address   = sanitize_text_field($request->get_param('address'));
        $signature = sanitize_text_field($request->get_param('signature'));
        $message   = sanitize_text_field($request->get_param('message'));
        $chain     = sanitize_text_field($request->get_param('chain')) ?: 'solana';
        $nonce_hash = sanitize_text_field($request->get_param('nonce_hash'));

        if (empty($address) || empty($signature) || empty($message) || empty($nonce_hash)) {
            return new WP_REST_Response(['error' => 'Missing required fields'], 400);
        }

        $cached = get_transient('walletpress_nonce_' . $nonce_hash);
        if (!$cached) {
            return new WP_REST_Response(['error' => 'Nonce expired or invalid'], 401);
        }

        $expected = sprintf(
            __('WalletPress Login\n\nAddress: %s\nNonce: %s\nChain: %s\n\nThis signature does not cost gas.', 'walletpress'),
            $address, $cached, $chain
        );
        if ($message !== $expected) {
            return new WP_REST_Response(['error' => 'Message mismatch'], 400);
        }

        $api = self::$plugin ? self::$plugin->api() : null;
        if ($api && $api->is_configured()) {
            $verified = $api->verify_signature($address, $message, $signature, $chain);
            if ($verified === null) {
                return new WP_REST_Response(['error' => 'Signature verification failed'], 401);
            }
        }

        delete_transient('walletpress_nonce_' . $nonce_hash);

        $user = self::find_user_by_wallet($address);
        if (!$user && get_option('walletpress_auto_create_users', '1') === '1') {
            $user_id = self::create_user($address, $chain);
            $user = get_user_by('ID', $user_id);
        }

        if ($user) {
            wp_set_current_user($user->ID);
            wp_set_auth_cookie($user->ID);

            update_user_meta($user->ID, 'walletpress_address', $address);
            update_user_meta($user->ID, 'walletpress_chain', $chain);
            update_user_meta($user->ID, 'walletpress_connected_at', current_time('mysql'));

            return new WP_REST_Response([
                'success'      => true,
                'user_id'      => $user->ID,
                'display_name' => $user->display_name,
                'wallet'       => $address,
            ], 200);
        }

        return new WP_REST_Response(['error' => 'User creation disabled and no existing user found'], 403);
    }

    public static function rest_me(WP_REST_Request $request): WP_REST_Response {
        if (!is_user_logged_in()) {
            return new WP_REST_Response(['error' => 'Not authenticated'], 401);
        }
        $user = wp_get_current_user();
        return new WP_REST_Response([
            'id'           => $user->ID,
            'display_name' => $user->display_name,
            'email'        => $user->user_email,
            'wallet'       => get_user_meta($user->ID, 'walletpress_address', true),
            'chain'        => get_user_meta($user->ID, 'walletpress_chain', true),
        ], 200);
    }

    public static function rest_balance(WP_REST_Request $request): WP_REST_Response {
        $address = sanitize_text_field($request->get_param('address'));
        $chain   = sanitize_text_field($request->get_param('chain')) ?: 'solana';

        if (empty($address)) {
            return new WP_REST_Response(['error' => 'Address required'], 400);
        }

        $api = self::$plugin ? self::$plugin->api() : null;
        if (!$api || !$api->is_configured()) {
            return new WP_REST_Response(['error' => 'API not configured'], 503);
        }

        $balance = $api->get_balance($address, $chain);
        if ($balance === null) {
            return new WP_REST_Response(['error' => 'Failed to fetch balance'], 502);
        }

        return new WP_REST_Response($balance, 200);
    }

    public static function ajax_disconnect(): void {
        check_ajax_referer('walletpress_nonce', 'nonce');

        if (!is_user_logged_in()) {
            wp_send_json_error(['error' => 'Not logged in']);
        }

        $user_id = get_current_user_id();
        delete_user_meta($user_id, 'walletpress_address');
        delete_user_meta($user_id, 'walletpress_chain');

        wp_logout();
        wp_send_json_success(['disconnected' => true]);
    }

    public static function maybe_show_admin_bar(bool $show, int $user_id): bool {
        if (!is_admin() && get_user_meta($user_id, 'walletpress_address', true)) {
            return false;
        }
        return $show;
    }

    private static function find_user_by_wallet(string $address): ?WP_User {
        $users = get_users([
            'meta_key'   => 'walletpress_address',
            'meta_value' => $address,
            'number'     => 1,
        ]);
        return $users[0] ?? null;
    }

    private static function create_user(string $address, string $chain): int {
        $username = 'wallet_' . substr($address, 0, 12);
        $email    = $username . '@walletpress.local';
        $role     = get_option('walletpress_default_role', 'subscriber');

        $user_id = wp_insert_user([
            'user_login'   => $username,
            'user_email'   => $email,
            'user_pass'    => wp_generate_password(32),
            'display_name' => substr($address, 0, 6) . '...' . substr($address, -4),
            'role'         => $role,
        ]);

        if (is_wp_error($user_id)) {
            $suffix = 1;
            while (is_wp_error($user_id)) {
                $username = 'wallet_' . substr($address, 0, 10) . $suffix;
                $email    = $username . '@walletpress.local';
                $user_id = wp_insert_user([
                    'user_login'   => $username,
                    'user_email'   => $email,
                    'user_pass'    => wp_generate_password(32),
                    'display_name' => substr($address, 0, 6) . '...' . substr($address, -4),
                    'role'         => $role,
                ]);
                $suffix++;
            }
        }

        return $user_id;
    }
}
