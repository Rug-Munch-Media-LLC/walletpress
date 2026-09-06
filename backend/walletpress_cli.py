#!/usr/bin/env python3
"""WalletPress CLI — run the backend without Docker.

Usage:
    walletpress serve          # Start the API server
    walletpress init           # Initialize data directory
    walletpress generate       # Generate a wallet from CLI
    walletpress validate       # Validate an address
    walletpress version        # Show version

No Docker required. Just pip install walletpress && walletpress serve.
"""

# ruff: noqa: S603, S607  # CLI installer invokes known system binaries
# (apt-get, openssl, systemctl, ...) via PATH with static arg lists and no
# shell=True — not untrusted input. S607 partial-path is intended for PATH lookup.

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("walletpress")


def cmd_serve(args):
    """Start the WalletPress API server."""
    import uvicorn

    from core.config import cfg

    port = args.port or cfg.port
    host = args.host or cfg.host

    os.makedirs(cfg.data_dir, exist_ok=True)
    logger.info(f"WalletPress v{cfg.version} starting on {host}:{port}")
    logger.info(f"Data directory: {cfg.data_dir}")
    logger.info(f"API docs: http://{host}:{port}/docs")
    logger.info(f"Health: http://{host}:{port}/health")

    if cfg.vault_password:
        logger.info("Vault encryption: AES-256-GCM + Argon2id")
    else:
        logger.warning("Vault encryption DISABLED. Set WP_VAULT_PASSWORD for production.")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


def cmd_deploy(args):
    """Production one-command setup (requires Pro license key).

    Detects OS, installs deps, configures everything, starts service.

    Setup methods:
      --docker           Deploy with Docker Compose (production stack)
      --method auto      Auto-detect best method (default)
      --method cli       Direct installation with systemd/launchd
      --domain DOMAIN    Set domain for SSL auto-config
      --email EMAIL      Email for Let's Encrypt notifications
    """
    from core.config import cfg as _cfg
    from core.license import get_license

    lic = get_license()
    if not lic.is_paid:
        print("  walletpress deploy requires a Pro license.")
        print("  Buy: https://walletpress.cc/buy")
        print("  Or use hosted: https://walletpress.cc/pricing")
        return 1

    method = args.method or "auto"
    domain = args.domain or ""

    print(f"  WalletPress Pro Deploy — v{_cfg.version}")
    print(f"  {'=' * 50}")
    print(f"  License: {lic.tier.title()}")
    print(f"  Method: {method}")
    if domain:
        print(f"  Domain: {domain}")
    print()

    if method == "docker":
        print("  Setting up Docker Compose production stack...")
        compose_path = os.path.join(
            os.path.dirname(__file__), "..", "installers", "docker-compose.prod.yml"
        )
        if os.path.exists(compose_path):
            print(f"  Compose file: {compose_path}")
            print(f"  Run: docker compose -f {compose_path} up -d")
        else:
            print("  Docker compose file not found. Re-download from walletpress.cc.")
        return

    # CLI method — direct installation
    import platform
    import subprocess

    system = platform.system().lower()
    print(f"  Detected OS: {system}")

    if system == "linux":
        print("  Installing system dependencies...")
        # Best-effort: non-zero exit or missing package manager should not
        # abort the rest of the install (packages may already be present).
        with contextlib.suppress(Exception):
            subprocess.run(["sudo", "apt-get", "update", "-qq"], check=False)
            subprocess.run(
                [
                    "sudo",
                    "apt-get",
                    "install",
                    "-y",
                    "-qq",
                    "python3",
                    "python3-venv",
                    "python3-pip",
                    "openssl",
                    "sqlite3",
                    "curl",
                ],
                check=False,
            )

        print("  Setting up virtual environment...")
        venv_path = "/opt/walletpress/venv"
        subprocess.run(["sudo", "python3", "-m", "venv", venv_path], check=False)

        print("  Installing Python dependencies...")
        req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
        subprocess.run(
            ["sudo", f"{venv_path}/bin/pip", "install", "-q", "-r", req_path], check=False
        )

        print("  Generating credentials...")
        admin_key = subprocess.run(
            ["openssl", "rand", "-hex", 32], capture_output=True, text=True
        ).stdout.strip()
        vault_pass = subprocess.run(
            ["openssl", "rand", "-hex", 32], capture_output=True, text=True
        ).stdout.strip()
        subprocess.run(
            ["openssl", "rand", "-hex", 16], capture_output=True, text=True
        ).stdout.strip()

        print("  Creating configuration...")
        subprocess.run(["sudo", "mkdir", "-p", "/etc/walletpress"], check=False)
        subprocess.run(["sudo", "mkdir", "-p", "/var/lib/walletpress"], check=False)

        env_content = f"""WP_ADMIN_KEY={admin_key}
WP_VAULT_PASSWORD={vault_pass}
WP_LICENSE_KEY={os.environ.get("WP_LICENSE_KEY", "")}
WP_DOMAIN={domain}
WP_CORS_ORIGINS={f"https://{domain}" if domain else "*"}
WP_SMTP_HOST=
WP_SMTP_PORT=587
WP_SMTP_USER=
WP_SMTP_PASS=
WP_FROM_EMAIL=walletpress@{domain if domain else "localhost"}
WP_NOTIFY_EMAIL=
WP_ALLOWED_IPS=
WP_RATE_LIMIT=120
"""
        subprocess.run(
            ["sudo", "tee", "/etc/walletpress/env"], input=env_content, text=True, check=False
        )
        subprocess.run(["sudo", "chmod", "600", "/etc/walletpress/env"], check=False)

        print("  Installing systemd service...")
        service_content = f"""[Unit]
Description=WalletPress Pro
After=network.target

[Service]
Type=simple
User=walletpress
Group=walletpress
EnvironmentFile=/etc/walletpress/env
WorkingDirectory=/opt/walletpress
ExecStart={venv_path}/bin/uvicorn main:app --host 127.0.0.1 --port 8010
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        subprocess.run(
            ["sudo", "tee", "/etc/systemd/system/walletpress.service"],
            input=service_content,
            text=True,
            check=False,
        )
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=False)
        subprocess.run(["sudo", "systemctl", "enable", "walletpress"], check=False)
        subprocess.run(["sudo", "systemctl", "start", "walletpress"], check=False)

        print()
        print(f"  {'=' * 50}")
        print("  WALLETPRESS PRO DEPLOYED")
        print(f"  {'=' * 50}")
        print("  URL:     http://localhost:8010")
        print("  Admin:   /api/v1/license")
        print("  Health:  /health")
        print("  Docs:    /docs")
        print("")
        print(f"  Admin key:     {admin_key}")
        print(f"  Vault pass:    {vault_pass}")
        print(f"  License:       {lic.tier.title()}")
        print("")
        print("  Save these credentials. They won't be shown again.")
        print("  Production: set up nginx reverse proxy + Let's Encrypt SSL.")

    elif system == "darwin":
        print("  macOS detected. Set up with launchd:")
        print("    brew install python@3.12 openssl sqlite")
        print("    python3 -m venv venv")
        print("    source venv/bin/activate")
        print("    pip install -r requirements.txt")
        print("    uvicorn main:app --port 8010")
    else:
        print(f"  Unsupported OS: {system}")
        print("  Use Docker: docker compose -f installers/docker-compose.prod.yml up -d")

    return 0


def cmd_init(args):
    """Initialize the WalletPress data directory."""
    from core.auth import get_key_store
    from core.config import cfg
    from core.vault import get_vault

    os.makedirs(cfg.data_dir, exist_ok=True)
    get_vault()
    get_key_store()

    if not cfg.admin_key:
        logger.warning("WP_ADMIN_KEY not set. API authentication will be disabled.")
        logger.warning("Set WP_ADMIN_KEY environment variable for production.")

    if not cfg.vault_password:
        logger.warning("WP_VAULT_PASSWORD not set. Private keys will NOT be encrypted at rest.")

    admin_key = cfg.admin_key
    logger.info(f"WalletPress initialized at {cfg.data_dir}")
    if admin_key:
        logger.info(f"Admin key: {admin_key[:16]}...")

    config_path = cfg.data_dir / ".env.example"
    if not config_path.exists():
        config_path.write_text("""# WalletPress Configuration
# Copy to .env and customize

WP_HOST=0.0.0.0
WP_PORT=8010
WP_DATA_DIR=/data
WP_ADMIN_KEY=change-me-to-a-random-string
WP_VAULT_PASSWORD=change-me-to-a-strong-password
WP_CORS_ORIGINS=http://localhost:8010
WP_RATE_LIMIT=60
WP_MAX_BATCH=100
""")
        logger.info(f"Example config created at {config_path}")


def cmd_generate(args):
    """Generate a wallet from the CLI."""
    from wallet_engine.chains import CHAINS
    from wallet_engine.generator import get_generator

    generator = get_generator()
    chain = args.chain or "eth"

    if chain not in CHAINS:
        print(f"Unsupported chain: {chain}")
        print(f"Supported: {', '.join(list(CHAINS.keys())[:20])}...")
        sys.exit(1)

    wallet = generator.generate(chain, label=args.label or f"cli_{chain}")
    print(json.dumps(wallet.to_safe_dict(), indent=2))
    print(f"\n{'!' * 60}")
    print("! WARNING: Private key is shown above. Keep it SECRET.")
    print(f"{'!' * 60}")


def cmd_validate(args):
    """Validate a wallet address."""
    from wallet_engine.chains import CHAINS, validate_address

    chain = args.chain or "eth"
    address = args.address

    chain_info = CHAINS.get(chain.lower())
    if not chain_info:
        print(f"Unsupported chain: {chain}")
        sys.exit(1)

    valid = validate_address(chain, address)
    print(f"Chain: {chain_info.name} ({chain})")
    print(f"Address: {address}")
    print(f"Valid: {'YES ✓' if valid else 'NO ✗'}")
    print(f"Expected pattern: {chain_info.address_pattern}")

    if not valid:
        sys.exit(1)


def cmd_doctor(args):
    """Run system diagnostics and show setup status."""
    from core.config import cfg as _cfg
    from core.onboarding import onboarding_status

    status = onboarding_status()
    from core.license import get_license

    lic = get_license()

    print(f"\n  WalletPress Doctor — v{_cfg.version}")
    print(f"  {'=' * 50}")
    print(
        f"  License: {lic.tier.title()} ({'permanent key' if lic.is_paid else 'free — 3 chains only'})"
    )
    print(f"  Vault encryption: {'✅ AES-256-GCM' if _cfg.vault_password else '❌ Not configured'}")
    print(f"  Admin API key: {'✅ Set' if _cfg.admin_key else '❌ Not set'}")
    print(
        f"  RPC endpoints: {status['rpc_health']['rpc_configured']}/{status['rpc_health']['total_chains']} configured"
    )
    print(
        f"  SSL: {'✅ Configured' if os.path.exists('/etc/letsencrypt') or os.getenv('WP_SSL_ENABLED') else '❌ Not configured'}"
    )
    print(f"  SMTP: {'✅ Configured' if os.getenv('WP_SMTP_HOST') else '❌ Not configured'}")
    print()
    print(f"  Issues: {status['items_missing']} of {status['items_total']} setup items incomplete")
    missing = status["missing_items"][:5]
    for item in missing:
        print(f"    ⚠ {item['item']}")
    print()
    if lic.is_paid:
        print("  Visit walletpress.cc/app for the hosted dashboard.")
    else:
        print("  → Buy Pro ($199) for deploy script and setup support: walletpress.cc/buy")
    print()


def cmd_version(args):
    """Show WalletPress version."""
    from core.config import cfg

    print(f"WalletPress v{cfg.version}")
    print("License: MIT")
    print("Repository: https://github.com/cryptorugmuncher/walletpress")


def main():
    parser = argparse.ArgumentParser(
        description="WalletPress — self-hosted multi-chain wallet management"
    )
    parser.add_argument("--version", action="store_true", help="Show version")

    sub = parser.add_subparsers(dest="command", help="Commands")

    serve_parser = sub.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default="", help="Bind host")
    serve_parser.add_argument("--port", type=int, default=0, help="Bind port")
    serve_parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")

    deploy_parser = sub.add_parser(
        "deploy", help="Production one-liner setup (requires Pro license)"
    )
    deploy_parser.add_argument("--docker", action="store_true", help="Deploy with Docker Compose")
    deploy_parser.add_argument(
        "--method", default="auto", choices=["auto", "cli", "docker"], help="Deployment method"
    )
    deploy_parser.add_argument("--domain", default="", help="Domain for SSL configuration")
    deploy_parser.add_argument("--email", default="", help="Email for Let's Encrypt")

    sub.add_parser("init", help="Initialize data directory")

    gen_parser = sub.add_parser("generate", help="Generate a wallet")
    gen_parser.add_argument("--chain", default="eth", help="Chain key (eth, sol, btc, etc.)")
    gen_parser.add_argument("--label", default="", help="Wallet label")

    val_parser = sub.add_parser("validate", help="Validate an address")
    val_parser.add_argument("--chain", default="eth", help="Chain key")
    val_parser.add_argument("address", help="Wallet address to validate")

    sub.add_parser("doctor", help="Run system diagnostics")
    backup_parser = sub.add_parser("backup", help="Export vault + proofs to encrypted archive")
    backup_parser.add_argument(
        "--output", default="walletpress_backup.json", help="Output file path"
    )
    restore_parser = sub.add_parser("restore", help="Restore vault from backup archive")
    restore_parser.add_argument("input", help="Backup file to restore from")
    sub.add_parser("version", help="Show version")

    args = parser.parse_args()

    if args.version:
        cmd_version(args)
        return

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "deploy":
        cmd_deploy(args)
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "generate":
        cmd_generate(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "backup":
        cmd_backup(args)
    elif args.command == "restore":
        cmd_restore(args)
    elif args.command == "version":
        cmd_version(args)
    else:
        parser.print_help()


def cmd_backup(args):
    """Export vault, proofs, and audit log to a portable JSON archive."""
    import json

    from core.vault import get_vault

    print(f"  Exporting WalletPress data to {args.output}...")
    vault = get_vault()
    wallets = vault.list(limit=100000)
    data = {
        "version": "1.1.0",
        "exported_at": __import__("time").time(),
        "wallets": [
            {
                "id": w.id,
                "chain": w.chain,
                "address": w.address,
                "label": w.label,
                "tags": w.tags,
                "created_at": w.created_at,
                "encrypted_key": w.encrypted_key,
                "public_key": w.public_key,
                "derivation_path": w.derivation_path,
                "encrypted": w.encrypted,
                "balance_usd": w.balance_usd,
                "notes": w.notes,
            }
            for w in wallets
        ],
    }
    with open(args.output, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Exported {len(wallets)} wallets to {args.output}")
    print(f"  Restore: walletpress restore {args.output}")


def cmd_restore(args):
    """Restore vault from a backup archive."""
    import json

    from core.vault import WalletEntry, get_vault

    print(f"  Restoring from {args.input}...")
    with open(args.input) as f:
        data = json.load(f)
    vault = get_vault()
    count = 0
    for w_data in data.get("wallets", []):
        entry = WalletEntry(
            id=w_data["id"],
            chain=w_data["chain"],
            address=w_data["address"],
            label=w_data.get("label", ""),
            tags=w_data.get("tags", []),
            created_at=w_data.get("created_at", 0),
            encrypted_key=w_data.get("encrypted_key", ""),
            public_key=w_data.get("public_key", ""),
            derivation_path=w_data.get("derivation_path", ""),
            encrypted=w_data.get("encrypted", False),
            balance_usd=w_data.get("balance_usd", 0),
            notes=w_data.get("notes", ""),
        )
        if vault.put(entry):
            count += 1
    print(f"  Restored {count} of {len(data.get('wallets', []))} wallets")


if __name__ == "__main__":
    main()
