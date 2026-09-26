"""Email outbound (verifikasi email / reset password).

Real send via SMTP (aiosmtplib) bila SMTP_ENABLED=1 + SMTP_HOST + SMTP_USER.
Tanpa itu = dev mode: send_email() return False, dan route boleh menampilkan
token/link langsung bila AUTH_DEV_VERIFY=1 (formula: tidak pernah membocorkan
link verifikasi ke produksi tanpa env eksplisit).
"""

import logging
import os

logger = logging.getLogger(__name__)


def email_enabled() -> bool:
    if os.getenv("SMTP_ENABLED", "0") != "1":
        return False
    return bool(os.getenv("SMTP_HOST")) and bool(os.getenv("SMTP_USER"))


def dev_verify_allowed() -> bool:
    return os.getenv("AUTH_DEV_VERIFY", "0") == "1"


def public_link_base() -> str:
    return os.getenv("PUBLIC_API_BASE_URL", "http://localhost:8080").rstrip("/")


async def send_email(to: str, subject: str, html: str, text: str | None = None) -> bool:
    """Kirim email. Return True bila terkirim, False bila SMTP off/staging.

    Raise bila SMTP aktif tapi gagal (route harus 503, bukan diam).
    """
    if not email_enabled():
        logger.info("SMTP off — email '%s' ke %s tidak dikirim (dev mode)", subject, to)
        return False
    import aiosmtplib

    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", "Ayesh <no-reply@ayesh.local>")
    use_tls = os.getenv("SMTP_STARTTLS", "1") == "1"

    message = (
        f"From: {from_addr}\r\n"
        f"To: {to}\r\n"
        f"Subject: {subject}\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "\r\n"
        f"{html}"
    )

    async with aiosmtplib.SMTP(hostname=host, port=port, timeout=15, use_tls=not use_tls) as client:
        if use_tls:
            await client.starttls()
        await client.login(user, password)
        await client.sendmail(from_addr, [to], message.encode("utf-8"))
    return True
