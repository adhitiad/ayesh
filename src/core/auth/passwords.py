"""Password hashing (Argon2id) + kebijakan minimum.

Argon2id = default modern (resistant GPU cracking). verify_password fail-closed:
segala bentuk error (format salah, corropt, dst) → False, bukan exception.
"""

import logging
import os

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored: str | None) -> bool:
    """True bila cocok. Salah format / error apa pun → False (fail-closed)."""
    if not password or not stored:
        return False
    try:
        return _hasher.verify(str(stored), password)
    except (VerificationError, VerifyMismatchError):
        return False
    except Exception:
        logging.getLogger(__name__).exception("Gagal verifikasi password (argon2)")
        return False


def password_policy_ok(password: str) -> tuple[bool, str | None]:
    """Cek kebijakan: panjang AUTH_MIN_PASSWORD_LEN (default 8) s.d. 128."""
    if not password or not isinstance(password, str):
        return False, "password wajib diisi"
    min_len = int(os.getenv("AUTH_MIN_PASSWORD_LEN", "8"))
    if len(password) < min_len:
        return False, f"password minimal {min_len} karakter"
    if len(password) > 128:
        return False, "password maksimal 128 karakter"
    return True, None
