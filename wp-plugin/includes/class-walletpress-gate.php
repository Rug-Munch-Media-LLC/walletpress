<?php
defined('ABSPATH') || exit;

class WalletPressGate {
    private static ?WalletPress $plugin = null;

    public function __construct(WalletPress $plugin) {
        self::$plugin = $plugin;
    }

    public static function render_gate(array $atts, string $content = ''): string {
        $atts = shortcode_atts([
            'id'         => '',
            'token'      => '',
            'chain'      => '',
            'min_amount' => '1',
            'fallback'   => '',
        ], $atts, 'wallet_gate');

        if (!is_user_logged_in()) {
            return self::fallback($atts['fallback']) ?: do_shortcode('[wallet_connect]');
        }

        $user = wp_get_current_user();
        $wallet = get_user_meta($user->ID, 'walletpress_address', true);
        $chain  = $atts['chain'] ?: get_user_meta($user->ID, 'walletpress_chain', true) ?: 'solana';

        if (!$wallet) {
            return self::fallback($atts['fallback']) ?: do_shortcode('[wallet_connect]');
        }

        if (!empty($atts['id'])) {
            $gates = get_option('walletpress_gates', []);
            $gate  = $gates[intval($atts['id'])] ?? null;
            if ($gate) {
                $atts['token']      = $gate['token'];
                $atts['chain']      = $gate['chain'];
                $atts['min_amount'] = $gate['min_amount'];
            }
        }

        if (empty($atts['token'])) {
            return $content ?: esc_html__('No token specified for gate.', 'walletpress');
        }

        $owns = self::check_ownership($wallet, $atts['token'], $chain, floatval($atts['min_amount']));

        if ($owns) {
            return do_shortcode($content);
        }

        return self::fallback($atts['fallback']);
    }

    public static function rest_verify_ownership(WP_REST_Request $request): WP_REST_Response {
        $address    = sanitize_text_field($request->get_param('address'));
        $contract   = sanitize_text_field($request->get_param('contract'));
        $chain      = sanitize_text_field($request->get_param('chain')) ?: 'solana';
        $min_amount = floatval($request->get_param('min_amount') ?: 1);

        if (empty($address) || empty($contract)) {
            return new WP_REST_Response(['error' => 'address and contract required'], 400);
        }

        $owns = self::check_ownership($address, $contract, $chain, $min_amount);

        return new WP_REST_Response([
            'owns'       => $owns,
            'address'    => $address,
            'contract'   => $contract,
            'chain'      => $chain,
            'min_amount' => $min_amount,
        ], 200);
    }

    private static function check_ownership(string $address, string $contract, string $chain, float $min_amount = 1): bool {
        $api = self::$plugin ? self::$plugin->api() : null;
        if ($api && $api->is_configured()) {
            $result = $api->check_ownership($address, $contract, $chain);
            if ($result !== null) {
                $balance = floatval($result['balance'] ?? $result['amount'] ?? 0);
                return $balance >= $min_amount;
            }
            $balance = $api->get_balance($address, $chain);
            if ($balance !== null) {
                $tokens = $balance['tokens'] ?? $balance['data']['tokens'] ?? [];
                foreach ($tokens as $token) {
                    $tok_addr = $token['address'] ?? $token['mint'] ?? '';
                    if (strtolower($tok_addr) === strtolower($contract)) {
                        $amount = floatval($token['amount'] ?? $token['balance'] ?? 0);
                        if ($amount >= $min_amount) {
                            return true;
                        }
                    }
                }
            }
        }
        return false;
    }

    private static function fallback(string $fallback): string {
        if (!empty($fallback)) {
            return '<div class="walletpress-gate-fallback">' . wp_kses_post($fallback) . '</div>';
        }
        return '<div class="walletpress-gate-fallback">' . esc_html__('You do not hold the required tokens to view this content.', 'walletpress') . '</div>';
    }
}
