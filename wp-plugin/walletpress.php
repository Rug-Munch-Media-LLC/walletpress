<?php
/**
 * Plugin Name:     WalletPress
 * Plugin URI:      https://walletpress.cc
 * Description:     Self-hosted wallet management platform. Generate, vault, analyze, distribute, and gate with crypto wallets across 55 chains. REST API + WP Admin + CLI.
 * Version:         1.0.0-beta
 * Author:          Rug Munch Media LLC
 * Author URI:      https://rugmunch.io
 * License:         GPL v2 or later
 * Text Domain:     walletpress
 * Domain Path:     /languages
 * Requires PHP:    8.1
 * Requires WP:     6.0
 */

defined('ABSPATH') || exit;

define('WALLETPRESS_VERSION', '1.0.0-beta');
define('WALLETPRESS_FILE', __FILE__);
define('WALLETPRESS_DIR', plugin_dir_path(__FILE__));
define('WALLETPRESS_URL', plugin_dir_url(__FILE__));

require_once WALLETPRESS_DIR . 'includes/class-walletpress.php';
require_once WALLETPRESS_DIR . 'includes/class-walletpress-admin.php';
require_once WALLETPRESS_DIR . 'includes/class-walletpress-api.php';
require_once WALLETPRESS_DIR . 'includes/class-walletpress-auth.php';
require_once WALLETPRESS_DIR . 'includes/class-walletpress-gate.php';
require_once WALLETPRESS_DIR . 'includes/class-walletpress-payments.php';

function walletpress(): WalletPress {
    static $instance = null;
    if ($instance === null) {
        $instance = new WalletPress();
    }
    return $instance;
}

walletpress()->init();
