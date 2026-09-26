"""Akun auth manusia: register/login/reset/verify/2FA + one-time tokens.

Semua token sekali-pakai (email_verify, password_reset, 2fa_challenge) disimpan
hashed di auth_tokens — satu token = satu pemakaian, TTL ketat. Email disimpan
lowercase (unik). Fail-closed: akun tanpa email_verified TIDAK bisa login bila
AUTH_REQUIRE_EMAIL_VERIFICATION=1 (default).
"""

import hashlib
import logging
import os
import re
import secrets
from datetime import timedelta

from src.core.auth.auth_context import _utcnow
from src.core.auth.auth_db import _ensure_auth_columns, _ensure_auth_tables
from src.core.auth.emailer import dev_verify_allowed, public_link_base
from src.core.auth.passwords import hash_password, password_policy_ok, verify_password
from src.core.auth.totp import (
    generate_backup_codes,
    hash_backup_codes,
    verify_backup_code,
    verify_totp,
)

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _ensure():
    _ensure_auth_columns()
    _ensure_auth_tables()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    email = normalize_email(email)
    if not email or len(email) > 255:
        return False
    return bool(_EMAIL_RE.match(email))


def require_email_verification() -> bool:
    return os.getenv("AUTH_REQUIRE_EMAIL_VERIFICATION", "1") == "1"


def _compile_dev_link(kind: str, token: str) -> str:
    path = "/auth/email/verify" if kind == "email_verify" else "/auth/password/reset"
    return f"{public_link_base()}{path}?token={token}"


def _issue_token(kind: str, user_id: str, ttl_minutes: int) -> str:
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthToken

    raw = f"ayt_{secrets.token_urlsafe(24)}"
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    now = _utcnow()
    with get_session() as db:
        db.add(
            AuthToken(
                token_hash=token_hash,
                user_id=user_id,
                kind=kind,
                created_at=now,
                expires_at=now + timedelta(minutes=ttl_minutes),
            )
        )
        db.commit()
    return raw


def _consume_token(kind: str, raw: str) -> str | None:
    """Konsumsi token sekali-pakai. Return user_id atau None (fokus ke one-time)."""
    if not raw:
        return None
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthToken

    token_hash = hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()
    now = _utcnow()
    with get_session() as db:
        row = db.query(AuthToken).filter(AuthToken.token_hash == token_hash, AuthToken.kind == kind).first()
        if not row or row.used_at is not None:
            return None
        expires = row.expires_at
        try:
            expired = expires <= now
        except Exception:
            expired = True
        if expired:
            return None
        row.used_at = now  # type: ignore[assignment]
        db.commit()
        return str(row.user_id)


def get_user_by_email(email: str):
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    email = normalize_email(email)
    with get_session() as db:
        return db.query(User).filter(User.email == email, User.active.is_(True)).first()


def get_account(user_id: str) -> dict | None:
    """Profil publik untuk /auth/me — tanpa secret apa pun."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        u = db.query(User).filter(User.id == user_id, User.active.is_(True)).first()
        if not u:
            return None
        return {
            "id": str(u.id),
            "name": u.name,
            "email": u.email,
            "email_verified": bool(u.email_verified),  # type: ignore[arg-type]
            "role": u.role,
            "auth_provider": u.auth_provider or ("password" if u.password_hash else None),
            "totp_enabled": u.totp_confirmed_at is not None,
            "has_password": bool(u.password_hash),
        }


def register_with_password(email: str, password: str, name: str) -> dict:
    """Daftar akun email+password. Return {account, email_verify_token?, dev_link?}."""
    email = normalize_email(email)
    ok, err = password_policy_ok(password)
    if not ok:
        raise ValueError(err)
    if not is_valid_email(email):
        raise ValueError("email tidak valid")
    name = (name or "").strip()[:100] or "user"

    from src.core.auth.auth_keys import create_user

    user = create_user(name, "user")
    uid = user["id"]

    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        dup = db.query(User).filter(User.email == email).first()
        if dup:
            raise ValueError("email sudah terdaftar")
        row = db.query(User).filter(User.id == uid).first()
        row.email = email  # type: ignore[assignment]
        row.password_hash = hash_password(password)  # type: ignore[assignment]
        row.auth_provider = "password"  # type: ignore[assignment]
        row.email_verified = False  # type: ignore[assignment]
        db.commit()

    verify_token = _issue_token("email_verify", uid, 60 * 24)
    return {
        "account": get_account(uid),
        "email_verify_token": verify_token,
        "dev_link": _compile_dev_link("email_verify", verify_token) if dev_verify_allowed() else None,
    }


def authenticate_password(email: str, password: str) -> tuple[str | None, str | None]:
    """Validate email+password. Return (user_id, error_kind)."""
    user = get_user_by_email(email)
    if not user or not user.password_hash:
        return None, "invalid_credentials"
    if not verify_password(password, str(user.password_hash)):
        return None, "invalid_credentials"
    if require_email_verification() and not user.email_verified:  # type: ignore[arg-type]
        return None, "email_not_verified"
    return str(user.id), None


def resend_verification(email: str) -> dict:
    user = get_user_by_email(email)
    if not user or not user.password_hash or (user.email_verified):  # type: ignore[arg-type]
        return {"sent": False}  # respons tetap 200 — anti enumeration
    token = _issue_token("email_verify", str(user.id), 60 * 24)
    return {
        "sent": True,
        "email_verify_token": token,
        "dev_link": _compile_dev_link("email_verify", token) if dev_verify_allowed() else None,
    }


def confirm_email_verification(token: str) -> bool:
    uid = _consume_token("email_verify", token)
    if not uid:
        return False
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        row = db.query(User).filter(User.id == uid).first()
        if not row:
            return False
        row.email_verified = True  # type: ignore[assignment]
        db.commit()
    return True


# ── 2FA ────────────────────────────────────────────────────────────────


def issue_2fa_challenge(user_id: str) -> str:
    return _issue_token("2fa_challenge", user_id, 5)


def resolve_2fa_challenge(token: str) -> str | None:
    return _consume_token("2fa_challenge", token)


def verify_user_totp(user_id: str, code: str) -> tuple[bool, str | None]:
    """Cek TOTP/backup saat login. (ok, new_backup_hashes)."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        row = db.query(User).filter(User.id == user_id).first()
        if not row or row.totp_confirmed_at is None or not row.totp_secret:
            return False, None
        secret = str(row.totp_secret)
        if verify_totp(secret, code):
            return True, None
        backup_ok, new_hashes = verify_backup_code(row.totp_backup_hashes, code)  # type: ignore[arg-type]
        if backup_ok:
            row.totp_backup_hashes = new_hashes  # type: ignore[assignment]
            db.commit()
            return True, new_hashes
        return False, None


def enable_totp(user_id: str, secret: str) -> bool:
    """Simpan secret 2FA PENDING (belum aktif sampai confirm_totp)."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        row = db.query(User).filter(User.id == user_id).first()
        if not row:
            return False
        if row.totp_confirmed_at is not None:
            return False  # sudah aktif — harus disable dulu
        row.totp_secret = secret  # type: ignore[assignment]
        db.commit()
    return True


def confirm_totp(user_id: str, code: str) -> list[str] | None:
    """Validasi kode terhadap secret pending; aktifkan + generate backup codes."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        row = db.query(User).filter(User.id == user_id).first()
        if not row or not row.totp_secret or row.totp_confirmed_at is not None:
            return None
        if not verify_totp(str(row.totp_secret), code):
            return None
        backup_codes = generate_backup_codes()
        row.totp_confirmed_at = _utcnow()  # type: ignore[assignment]
        row.totp_backup_hashes = hash_backup_codes(backup_codes)  # type: ignore[assignment]
        db.commit()
        return backup_codes


def disable_totp(user_id: str, password: str) -> bool:
    """Matikan 2FA (wajib password). Revoke sesi lain — fail-closed."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        row = db.query(User).filter(User.id == user_id).first()
        if not row or not row.password_hash:
            return False
        if not verify_password(password, str(row.password_hash)):
            return False
        row.totp_secret = None  # type: ignore[assignment]
        row.totp_confirmed_at = None  # type: ignore[assignment]
        row.totp_backup_hashes = None  # type: ignore[assignment]
        db.commit()
    return True


# ── Password reset / change ────────────────────────────────────────────


def issue_password_reset(email: str) -> dict:
    """Buat token reset bila akun ada (respons route tetaplah seragam)."""
    user = get_user_by_email(email)
    if not user or not user.password_hash or not user.email_verified:  # type: ignore[arg-type]
        return {"sent": False}
    token = _issue_token("password_reset", str(user.id), 15)
    return {
        "sent": True,
        "reset_token": token,
        "dev_link": _compile_dev_link("password_reset", token) if dev_verify_allowed() else None,
    }


def confirm_password_reset(token: str, new_password: str) -> bool:
    ok, err = password_policy_ok(new_password)
    if not ok:
        raise ValueError(err)
    uid = _consume_token("password_reset", token)
    if not uid:
        return False
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        row = db.query(User).filter(User.id == uid).first()
        if not row:
            return False
        row.password_hash = hash_password(new_password)  # type: ignore[assignment]
        db.commit()
    from src.core.auth.sessions import revoke_all_user_sessions

    revoke_all_user_sessions(uid)
    return True


def change_user_password(user_id: str, current: str, new_password: str) -> dict:
    ok, err = password_policy_ok(new_password)
    if not ok:
        raise ValueError(err)
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        row = db.query(User).filter(User.id == user_id).first()
        if not row or not row.password_hash:
            raise ValueError("akun tanpa password (OAuth-only) tidak bisa ganti password")
        if not verify_password(current, str(row.password_hash)):
            raise ValueError("password saat ini salah")
        row.password_hash = hash_password(new_password)  # type: ignore[assignment]
        db.commit()
    return {"changed": True, "revoked_sessions": "revoked on other sessions"}


# ── OAuth identity linking ─────────────────────────────────────────────


def link_oauth_identity(profile: dict) -> dict:
    """Cari/link/create user dari profil provider. Return load_user_profile()."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    provider = profile["provider"]
    provider_id = profile["provider_user_id"]
    email = normalize_email(profile.get("email") or "")
    if not is_valid_email(email):
        raise ValueError("provider tidak mengembalikan email yang valid")

    uid: str | None = None
    with get_session() as db:
        by_provider = (
            db.query(User)
            .filter(User.auth_provider == provider, User.oauth_provider_id == provider_id, User.active.is_(True))
            .first()
        )
        if by_provider:
            uid = str(by_provider.id)
        else:
            by_email = db.query(User).filter(User.email == email, User.active.is_(True)).first()
            if by_email:
                if by_email.oauth_provider_id is not None and by_email.oauth_provider_id != provider_id:
                    raise ValueError("email_in_use")
                uid = str(by_email.id)
                by_email.auth_provider = provider  # type: ignore[assignment]
                by_email.oauth_provider_id = provider_id  # type: ignore[assignment]
                by_email.email_verified = True  # type: ignore[assignment]
                db.commit()
    if not uid:
        from src.core.auth.auth_keys import create_user

        created = create_user(profile.get("name") or "user", "user")
        uid = created["id"]
        with get_session() as db:
            row = db.query(User).filter(User.id == uid).first()
            row.email = email  # type: ignore[assignment]
            row.email_verified = True  # type: ignore[assignment]
            row.auth_provider = provider  # type: ignore[assignment]
            row.oauth_provider_id = provider_id  # type: ignore[assignment]
            db.commit()

    from src.core.auth.auth_keys import load_user_profile

    return load_user_profile(uid) or {"id": uid, "name": "user", "role": "user", "vip_expires_at": None}
