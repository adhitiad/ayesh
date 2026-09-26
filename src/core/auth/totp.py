"""TOTP 2FA (RFC 6238 via pyotp) + backup codes sekali-pakai.

Backup code: 8 karakter format `XXXX-XXXX`. Disimpan HASH (sha256) dalam JSON
list; kode yang sudah dipakai dihapus (one-time).
"""

import hashlib
import json
import secrets

import pyotp


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Ayesh")


def verify_totp(secret: str, code: str) -> bool:
    code = (code or "").strip()
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


def _norm_code(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "-")


def generate_backup_codes(n: int = 10) -> list[str]:
    codes: list[str] = []
    for _ in range(n):
        block = "-".join(secrets.token_hex(2).upper() for _ in range(2))
        codes.append(block)
    return codes


def hash_backup_codes(codes: list[str]) -> str:
    hashes = [hashlib.sha256(c.encode("utf-8")).hexdigest() for c in codes]
    return json.dumps(hashes)


def verify_backup_code(stored_hashes: str | None, code: str) -> tuple[bool, str | None]:
    """Cek backup code. (ok, new_stored) — new_stored != None bila kode terpakai."""
    if not stored_hashes or not code:
        return False, None
    try:
        hashes = json.loads(stored_hashes)
        if not isinstance(hashes, list):
            return False, None
    except (ValueError, TypeError):
        return False, None
    target = hashlib.sha256(_norm_code(code).encode("utf-8")).hexdigest()
    for i, stored in enumerate(hashes):
        if str(stored) == target:
            remaining = list(hashes)
            remaining.pop(i)
            return True, json.dumps(remaining)
    return False, None
