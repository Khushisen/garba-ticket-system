"""
QR / secure token generation.

Security model:
- The RAW token is a cryptographically secure random string (secrets.token_urlsafe),
  long enough to be unguessable. It is embedded in the QR code / PDF only.
- The database stores only SHA-256(raw_token) — never the raw token itself.
  This means a database leak alone cannot be used to forge working QR codes.
- Verification takes a raw token from a scanned QR, hashes it, and looks up the hash.
"""

import hashlib
import io
import secrets

import qrcode
from qrcode.image.pil import PilImage


def generate_raw_token(num_bytes: int = 32) -> str:
    """Cryptographically secure, URL-safe, unpredictable token (~43 chars for 32 bytes)."""
    return secrets.token_urlsafe(num_bytes)


def generate_secure_slug(num_bytes: int = 16) -> str:
    """Separate secret used for the public /ticket/<slug> URL (distinct from the QR token,
    so leaking one does not compromise the other)."""
    return secrets.token_urlsafe(num_bytes)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def build_qr_payload_url(base_url: str, raw_token: str) -> str:
    return f"{base_url.rstrip('/')}/verify/{raw_token}"


def generate_qr_png_bytes(data: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
