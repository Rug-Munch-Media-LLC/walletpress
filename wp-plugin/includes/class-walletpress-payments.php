<?php
defined('ABSPATH') || exit;

class WalletPressPayments {
    private static ?WalletPress $plugin = null;

    public function __construct(WalletPress $plugin) {
        self::$plugin = $plugin;
    }

    public static function render_pay_button(array $atts): string {
        $atts = shortcode_atts([
            'amount'    => '10',
            'token'     => 'SOL',
            'chain'     => 'solana',
            'to'        => '',
            'label'     => '',
            'product'   => '',
            'success'   => '',
        ], $atts, 'wallet_pay');

        $to_address = $atts['to'] ?: get_option('walletpress_merchant_wallet', '');

        if (empty($to_address)) {
            return '<p class="walletpress-error">' . esc_html__('Payment not configured. Set a merchant wallet in settings.', 'walletpress') . '</p>';
        }

        $label = $atts['label'] ?: sprintf(__('Pay %s %s', 'walletpress'), $atts['amount'], $atts['token']);

        ob_start();
        ?>
        <div class="walletpress-payment" data-amount="<?php echo esc_attr($atts['amount']); ?>" data-token="<?php echo esc_attr($atts['token']); ?>" data-chain="<?php echo esc_attr($atts['chain']); ?>" data-to="<?php echo esc_attr($to_address); ?>" data-product="<?php echo esc_attr($atts['product']); ?>" data-success="<?php echo esc_attr($atts['success']); ?>">
            <button class="walletpress-btn walletpress-btn-pay">
                <?php echo esc_html($label); ?>
            </button>
            <div class="walletpress-payment-status" style="display:none;"></div>
            <div class="walletpress-payment-qr" style="display:none;"></div>
        </div>
        <?php
        return ob_get_clean();
    }

    public static function rest_create_payment(WP_REST_Request $request): WP_REST_Response {
        $from   = sanitize_text_field($request->get_param('from'));
        $amount = floatval($request->get_param('amount'));
        $token  = sanitize_text_field($request->get_param('token')) ?: 'SOL';
        $chain  = sanitize_text_field($request->get_param('chain')) ?: 'solana';
        $to     = sanitize_text_field($request->get_param('to'));

        if (empty($from) || empty($to)) {
            return new WP_REST_Response(['error' => 'from and to required'], 400);
        }

        $api = self::$plugin ? self::$plugin->api() : null;
        if ($api && $api->is_configured()) {
            $result = $api->create_payment($from, $to, $amount, $token, $chain);
            if ($result) {
                return new WP_REST_Response($result, 200);
            }
        }

        return new WP_REST_Response([
            'from'   => $from,
            'to'     => $to,
            'amount' => $amount,
            'token'  => $token,
            'chain'  => $chain,
            'status' => 'pending',
        ], 200);
    }

    public static function rest_verify_payment(WP_REST_Request $request): WP_REST_Response {
        $tx_hash = sanitize_text_field($request->get_param('tx_hash'));
        $chain   = sanitize_text_field($request->get_param('chain')) ?: 'solana';
        $product = sanitize_text_field($request->get_param('product'));

        if (empty($tx_hash)) {
            return new WP_REST_Response(['error' => 'tx_hash required'], 400);
        }

        $api = self::$plugin ? self::$plugin->api() : null;
        if ($api && $api->is_configured()) {
            $result = $api->verify_payment($tx_hash, $chain);
            if ($result !== null && !empty($result['confirmed'])) {
                if (!empty($product)) {
                    self::unlock_product($tx_hash, $product);
                }
                return new WP_REST_Response(array_merge($result, ['unlocked' => true]), 200);
            }
        }

        return new WP_REST_Response(['tx_hash' => $tx_hash, 'confirmed' => false, 'status' => 'pending'], 200);
    }

    private static function unlock_product(string $tx_hash, string $product): void {
        if (!is_user_logged_in()) {
            return;
        }
        $user_id = get_current_user_id();
        $purchases = get_user_meta($user_id, 'walletpress_purchases', true) ?: [];
        if (!in_array($product, $purchases, true)) {
            $purchases[] = $product;
            update_user_meta($user_id, 'walletpress_purchases', $purchases);
        }
    }
}
