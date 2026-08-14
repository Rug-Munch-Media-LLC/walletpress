"""PDF generation for paper wallets and birth certificates."""

from __future__ import annotations

import io
import logging
import time

from core.config import cfg

logger = logging.getLogger("wp.pdf")

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

try:
    import qrcode

    HAS_QR = True
except ImportError:
    HAS_QR = False


def _qr_image(data: str, size: int = 200) -> ImageReader | None:
    if not HAS_QR:
        return None
    import io

    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def generate_paper_wallet(
    address: str,
    chain: str,
    private_key: str = "",
    public_key: str = "",
    derivation_path: str = "",
    created_at: float = 0.0,
    proof_leaf: str = "",
    label: str = "",
) -> bytes | None:
    """Generate a printable paper wallet PDF.

    Returns PDF bytes or None if reportlab is not installed.
    Paper wallets are for cold storage. Print on durable paper. Store safely.
    """
    if not HAS_REPORTLAB:
        return None

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    margin = 0.75 * inch
    y = h - margin

    # Title
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margin, y, "WALLETPRESS PAPER WALLET")
    y -= 30
    c.setFont("Helvetica", 10)
    c.drawString(
        margin,
        y,
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(created_at or time.time()))}",
    )
    y -= 14
    c.drawString(margin, y, f"Software: WalletPress Pro v{cfg.version}")
    y -= 14
    c.drawString(margin, y, "Chain: " + chain.upper())
    y -= 14
    if label:
        c.drawString(margin, y, f"Label: {label}")
        y -= 14
    y -= 20

    # Warning box
    c.setFillColorRGB(1, 0.9, 0.9)
    c.rect(margin, y - 50, w - 2 * margin, 50, fill=1, stroke=0)
    c.setFillColorRGB(0.8, 0, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin + 8, y - 16, "⚠ KEEP THIS DOCUMENT SECURE")
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.5, 0, 0)
    c.drawString(
        margin + 8,
        y - 32,
        "Anyone with this paper can control the crypto assets. Store in a safe, waterproof location.",
    )
    c.setFillColorRGB(0, 0, 0)
    y -= 70

    # Address section
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, "Public Address")
    y -= 16
    c.setFont("Courier", 9)
    c.drawString(margin, y, address)
    y -= 30

    # QR code for address
    qr = _qr_image(f"{chain}:{address}")
    if qr:
        c.drawImage(qr, margin, y - 100, width=100, height=100)
    y -= 120

    # Private key section
    if private_key:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColorRGB(0.8, 0, 0)
        c.drawString(margin, y, "PRIVATE KEY (KEEP SECRET)")
        y -= 16
        c.setFont("Courier", 8)
        c.setFillColorRGB(0, 0, 0)
        # Split long key into lines
        key_lines = [private_key[i : i + 48] for i in range(0, len(private_key), 48)]
        for line in key_lines:
            c.drawString(margin, y, line)
            y -= 12
        y -= 10

    # Public key
    if public_key:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin, y, "Public Key")
        y -= 14
        c.setFont("Courier", 7)
        pk_lines = [public_key[i : i + 64] for i in range(0, len(public_key), 64)]
        for line in pk_lines[:4]:
            c.drawString(margin, y, line)
            y -= 10
        y -= 10

    # Derivation path
    if derivation_path:
        c.setFont("Helvetica", 9)
        c.drawString(margin, y, f"Derivation: {derivation_path}")
        y -= 14

    # Proof hash
    if proof_leaf:
        c.setFont("Helvetica", 7)
        c.drawString(margin, y, f"Proof: {proof_leaf[:48]}...")
        y -= 10

    # Footer
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(
        margin, margin * 0.5, f"WalletPress Pro — walletpress.cc — {cfg.version} — MIT Open Source"
    )

    c.save()
    return buf.getvalue()


def generate_birth_certificate(
    wallet_id: str,
    address: str,
    chain: str,
    public_key: str = "",
    created_at: float = 0.0,
    proof_leaf: str = "",
    root_hash: str = "",
    committed: bool = False,
) -> bytes | None:
    """Generate a Wallet Birth Certificate — printable provenance document.

    This is a unique feature. It cryptographically proves when and how
    this wallet was created. The Proof of Generation hash links this
    document to the immutable audit trail.
    """
    if not HAS_REPORTLAB:
        return None

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    margin = 0.75 * inch
    y = h - margin

    # Certificate border
    c.setStrokeColorRGB(0.77, 0.55, 0.30)
    c.setLineWidth(3)
    c.rect(margin - 10, margin - 10, w - 2 * margin + 20, h - 2 * margin + 20)

    # Seal graphic
    c.setFillColorRGB(0.77, 0.55, 0.30)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(margin, y, "✦ WALLET BIRTH CERTIFICATE ✦")
    y -= 36
    c.setFont("Helvetica", 12)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(margin, y, "This certifies that the following wallet was generated by WalletPress")
    y -= 14
    c.drawString(
        margin, y, "with cryptographic proof of its creation time, code version, and integrity."
    )
    y -= 30

    # Details
    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(0, 0, 0)
    details = [
        ("Wallet ID", wallet_id),
        ("Address", address),
        ("Chain", chain.upper()),
        ("Created", time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(created_at))),
        ("Public Key", public_key[:48] + "..." if len(public_key) > 48 else public_key),
    ]
    for label, value in details:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, y, label + ":")
        c.setFont("Courier", 9)
        c.drawString(margin + 100, y, value)
        y -= 16

    y -= 10

    # Proof section
    c.setStrokeColorRGB(0.77, 0.55, 0.30)
    c.setLineWidth(1)
    c.rect(margin, y - 50, w - 2 * margin, 50)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 6, y - 14, "Proof of Generation — Merkle Attestation")
    c.setFont("Courier", 7)
    c.drawString(margin + 6, y - 28, f"Leaf: {proof_leaf}")
    if root_hash:
        c.drawString(margin + 6, y - 40, f"Root: {root_hash}")
    y -= 70

    # QR for verification
    qr = _qr_image(f"https://walletpress.cc/api/v1/proof/verify/{wallet_id}")
    if qr:
        c.drawImage(qr, w - margin - 100, y - 100, width=100, height=100)

    y -= 120

    # Trust text
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(margin, y, "Verify: walletpress.cc/api/v1/proof/verify/{wallet_id}")
    y -= 10
    c.drawString(
        margin, y, f"Software: WalletPress Pro v{cfg.version} — MIT Open Source — walletpress.cc"
    )

    c.save()
    return buf.getvalue()
