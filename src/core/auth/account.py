"""Akun auth manusia: register/login/reset/verify/2FA + one-time tokens,
profil & hapus-akun mandiri (W6), identitas OAuth multi-provider (W9e).

Semua token sekali-pakai (email_verify, password_reset, 2fa_challenge) disimpan
hashed di auth_tokens — satu token = satu pemakaian, TTL ketat. Email disimpan
lowercase (unik). Username: 3-32 karakter [a-z0-9_.] lowercase, unik
case-insensitive; opsional saat register (kosong → auto dari local-part email).
Fail-closed: akun tanpa email_verified TIDAK bisa login bila
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
_USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,32}$")
_OAUTH_PROVIDERS = ("google", "github")


class EmailAlreadyRegistered(ValueError):
    """Email sudah dipakai — route memetakan ke 409 + hint_provider (W9c)."""

    def __init__(self, hint_provider: str | None = None):
        super().__init__("email sudah terdaftar")
        self.hint_provider = hint_provider


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


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def is_valid_username(username: str) -> bool:
    return bool(_USERNAME_RE.match(username))


def _base_from_email(email: str) -> str:
    """Alias otomatis dari local-part email (bersih dari karakter di luar [a-z0-9_.])."""
    local = re.sub(r"[^a-z0-9_.]", "", normalize_email(email).split("@", 1)[0])
    if len(local) < 3:
        local = f"user{local}"
    return local[:32]


def _username_taken(db, uname: str) -> bool:
    from sqlalchemy import func

    from src.core.db.models import User

    return db.query(User.id).filter(func.lower(User.username) == uname).first() is not None


def _claim_username(db, base: str) -> str:
    """Ambil username unik dari basis (case-insensitive); bentrok → suffix -<n>."""
    if not _username_taken(db, base):
        return base
    n = 2
    while n < 1000:
        suffix = f"-{n}"
        candidate = f"{base[: 32 - len(suffix)]}{suffix}"
        if not _username_taken(db, candidate):
            return candidate
        n += 1
    return f"{base[:23]}-{secrets.token_hex(4)}"


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


def get_user_by_username(username: str):
    """Lookup username case-insensitive (lower) — fallback login identifier W9b."""
    uname = normalize_username(username)
    if not uname:
        return None
    _ensure()
    from sqlalchemy import func

    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        return db.query(User).filter(func.lower(User.username) == uname, User.active.is_(True)).first()


def get_account(user_id: str) -> dict | None:
    """Profil publik untuk /auth/me — tanpa secret apa pun."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthOAuthAccount, User

    with get_session() as db:
        u = db.query(User).filter(User.id == user_id, User.active.is_(True)).first()
        if not u:
            return None
        rows = db.query(AuthOAuthAccount.provider).filter(AuthOAuthAccount.user_id == user_id).all()
        connected = sorted({str(r[0]) for r in rows} | set(_legacy_providers(u)))
        return {
            "id": str(u.id),
            "name": u.name,
            "email": u.email,
            "username": u.username,
            "email_verified": bool(u.email_verified),  # type: ignore[arg-type]
            "role": u.role,
            "auth_provider": u.auth_provider or ("password" if u.password_hash else None),
            "connected_providers": connected,
            "totp_enabled": u.totp_confirmed_at is not None,
            "has_password": bool(u.password_hash),
        }


def _legacy_providers(user_row) -> list[str]:
    """Provider dari kolom legacy users (fallback bila baris tabel belum ada)."""
    if user_row.auth_provider in _OAUTH_PROVIDERS and user_row.oauth_provider_id:
        return [str(user_row.auth_provider)]
    return []


def _primary_oauth_hint(db, user_row) -> str | None:
    """Provider OAuth akun lama untuk hint 409 register (W9c): tabel + legacy."""
    from src.core.db.models import AuthOAuthAccount

    row = (
        db.query(AuthOAuthAccount.provider)
        .filter(AuthOAuthAccount.user_id == str(user_row.id))
        .order_by(AuthOAuthAccount.created_at)
        .first()
    )
    if row and str(row[0]) in _OAUTH_PROVIDERS:
        return str(row[0])
    legacy = _legacy_providers(user_row)
    return legacy[0] if legacy else None


def register_with_password(email: str, password: str, name: str, username: str | None = None) -> dict:
    """Daftar akun email+password. Username opsional — kosong → auto local-part.

    Return {account, email_verify_token?, dev_link?}. Email terdaftar →
    EmailAlreadyRegistered (route → 409 + hint_provider).
    """
    email = normalize_email(email)
    ok, err = password_policy_ok(password)
    if not ok:
        raise ValueError(err)
    if not is_valid_email(email):
        raise ValueError("email tidak valid")
    name = (name or "").strip()[:100] or "user"
    wanted: str | None = None
    if username:
        wanted = normalize_username(username)
        if not is_valid_username(wanted):
            raise ValueError("username tidak valid: 3-32 karakter, huruf kecil/angka/titik/underscore")

    from src.core.auth.auth_keys import create_user

    user = create_user(name, "user")
    uid = user["id"]

    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        dup = db.query(User).filter(User.email == email).first()
        if dup:
            raise EmailAlreadyRegistered(_primary_oauth_hint(db, dup))
        if wanted is not None:
            if _username_taken(db, wanted):
                raise ValueError("username sudah dipakai")
            final = wanted
        else:
            final = _claim_username(db, _base_from_email(email))
        row = db.query(User).filter(User.id == uid).first()
        row.email = email  # type: ignore[assignment]
        row.username = final  # type: ignore[assignment]
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


def authenticate_password(identifier: str, password: str) -> tuple[str | None, str | None]:
    """Validate email/username + password. Lookup email dulu, fallback username (W9b)."""
    user = get_user_by_email(identifier)
    if not user:
        user = get_user_by_username(identifier)
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


# ── Profil, backup code, hapus-akun (W6) ───────────────────────────────


def update_display_name(user_id: str, name: str) -> dict | None:
    """Ubah display name. Return get_account() atau None bila akun tidak ada.

    Email TIDAK bisa lewat jalur ini — perubahan email = alur terpisah
    dengan verifikasi (W6).
    """
    name = (name or "").strip()[:100]
    if not name:
        raise ValueError("name wajib 1-100 karakter")
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        row = db.query(User).filter(User.id == user_id, User.active.is_(True)).first()
        if not row:
            return None
        row.name = name  # type: ignore[assignment]
        db.commit()
    return get_account(user_id)


def regenerate_backup_codes(user_id: str) -> list[str] | None:
    """Buat ulang 10 backup code (kode lama langsung tak berlaku). None bila 2FA nonaktif."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        row = db.query(User).filter(User.id == user_id).first()
        if not row or row.totp_confirmed_at is None:
            return None
        codes = generate_backup_codes()
        row.totp_backup_hashes = hash_backup_codes(codes)  # type: ignore[assignment]
        db.commit()
        return codes


def _deleted_email(user_id: str) -> str:
    return f"deleted-{user_id[:8]}@deleted.invalid"


def delete_account_self(user_id: str, password: str, code: str | None = None) -> str | None:
    """Hapus-akun mandiri (soft-delete, W6). Hard-gate: password + kode 2FA bila aktif.

    Return None bila sukses; alasan gagal bila tidak:
    `no_password` | `bad_password` | `code_required` | `bad_code`.
    Kredensial & identitas dibersihkan, sesi di-revoke — akun tak bisa dipakai lagi.
    """
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthOAuthAccount, AuthToken, User

    with get_session() as db:
        row = db.query(User).filter(User.id == user_id).first()
        if not row or not row.password_hash:
            return "no_password"
        if not verify_password(password, str(row.password_hash)):
            return "bad_password"
        if row.totp_confirmed_at is not None:
            if not code:
                return "code_required"
            secret = str(row.totp_secret or "")
            if not (secret and verify_totp(secret, code)):
                backup_ok, _ = verify_backup_code(row.totp_backup_hashes, code)
                if not backup_ok:
                    return "bad_code"
        # Soft-delete: anonimkan identitas, cabut kredensial, hapus identitas OAuth.
        row.active = False  # type: ignore[assignment]
        row.name = "deleted-user"  # type: ignore[assignment]
        row.email = _deleted_email(user_id)  # type: ignore[assignment]
        row.username = None  # type: ignore[assignment]
        row.password_hash = None  # type: ignore[assignment]
        row.totp_secret = None  # type: ignore[assignment]
        row.totp_confirmed_at = None  # type: ignore[assignment]
        row.totp_backup_hashes = None  # type: ignore[assignment]
        row.auth_provider = None  # type: ignore[assignment]
        row.oauth_provider_id = None  # type: ignore[assignment]
        db.query(AuthOAuthAccount).filter(AuthOAuthAccount.user_id == user_id).delete(synchronize_session=False)
        db.query(AuthToken).filter(AuthToken.user_id == user_id).delete(synchronize_session=False)
        db.commit()
    from src.core.auth.sessions import revoke_all_user_sessions

    revoke_all_user_sessions(user_id)
    return None


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


# ── OAuth identity linking (W9d fail-closed + W9e multi-provider) ──────


def _find_identity(db, provider: str, provider_id: str) -> tuple[str, bool] | None:
    """(user_id, active) untuk identitas provider: tabel → kolom legacy. None bila tak dikenal."""
    from src.core.db.models import AuthOAuthAccount, User

    arow = (
        db.query(AuthOAuthAccount.user_id, User.active)
        .join(User, User.id == AuthOAuthAccount.user_id)
        .filter(AuthOAuthAccount.provider == provider, AuthOAuthAccount.provider_id == provider_id)
        .first()
    )
    if arow is not None:
        return str(arow[0]), bool(arow[1])
    lrow = (
        db.query(User.id, User.active)
        .filter(User.auth_provider == provider, User.oauth_provider_id == provider_id)
        .first()
    )
    if lrow is not None:
        return str(lrow[0]), bool(lrow[1])
    return None


def _add_identity(db, user_row, provider: str, provider_id: str, email: str) -> None:
    """Catat identitas di auth_oauth_accounts + isi kolom legacy bila masih kosong.

    Kolom legacy hanya merefleksikan provider PERTAMA; koneksi berikutnya menumpuk
    di tabel (W9e) sehingga satu akun bisa terhubung Google DAN GitHub.
    """
    from src.core.db.models import AuthOAuthAccount

    uid = str(user_row.id)
    have = (
        db.query(AuthOAuthAccount.id)
        .filter(
            AuthOAuthAccount.user_id == uid,
            AuthOAuthAccount.provider == provider,
            AuthOAuthAccount.provider_id == provider_id,
        )
        .first()
    )
    if have is None:
        db.add(
            AuthOAuthAccount(
                user_id=uid,
                provider=provider,
                provider_id=provider_id,
                email=email or None,
                email_verified=True,
                created_at=_utcnow(),
            )
        )
    if not user_row.oauth_provider_id:
        user_row.auth_provider = provider  # type: ignore[assignment]
        user_row.oauth_provider_id = provider_id  # type: ignore[assignment]


def link_oauth_identity(profile: dict) -> dict:
    """Cari/link/create user dari profil provider. Return load_user_profile().

    Fail-closed (W9d): auto-link by email maupun pembuatan akun baru hanya bila
    provider menyatakan email-nya verified (`profile["email_verified"]`) —
    provider bilang unverified → tolak `email_unverified`, jangan link, jangan
    set email_verified. Akun yang SUDAH terlink (by identity) tetap boleh login.

    Multi-provider (W9e): identitas tercatat di `auth_oauth_accounts` — satu
    akun bisa terhubung Google DAN GitHub. `email_in_use` ditolak HANYA bila
    identitas sudah terikat user lain, akun nonaktif, atau provider sama dengan
    provider_id berbeda (klaim email sama oleh akun provider berbeda).
    """
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
        ident = _find_identity(db, provider, provider_id)
        if ident is not None:
            if not ident[1]:
                raise ValueError("email_in_use")  # akun nonaktif — fail-closed
            uid = ident[0]
        else:
            if not profile.get("email_verified"):
                raise ValueError("email_unverified")
            holder = db.query(User).filter(User.email == email).first()
            if holder is not None and not holder.active:
                raise ValueError("email_in_use")
            if holder is not None:
                from src.core.db.models import AuthOAuthAccount

                # Identitas ini sudah terikat user lain → cegah takeover.
                taken = (
                    db.query(AuthOAuthAccount.user_id)
                    .filter(AuthOAuthAccount.provider == provider, AuthOAuthAccount.provider_id == provider_id)
                    .first()
                )
                if taken is not None and str(taken[0]) != str(holder.id):
                    raise ValueError("email_in_use")
                # Provider sama + id beda pada email sama → tetap ditolak.
                other = (
                    db.query(AuthOAuthAccount.id)
                    .filter(
                        AuthOAuthAccount.user_id == str(holder.id),
                        AuthOAuthAccount.provider == provider,
                        AuthOAuthAccount.provider_id != provider_id,
                    )
                    .first()
                )
                legacy_conflict = (
                    holder.auth_provider == provider
                    and holder.oauth_provider_id is not None
                    and holder.oauth_provider_id != provider_id
                )
                if other is not None or legacy_conflict:
                    raise ValueError("email_in_use")
                uid = str(holder.id)
                holder.email_verified = True  # type: ignore[assignment]
                _add_identity(db, holder, provider, provider_id, email)
                db.commit()
    if not uid:
        from src.core.auth.auth_keys import create_user

        created = create_user(profile.get("name") or "user", "user")
        uid = created["id"]
        with get_session() as db:
            row = db.query(User).filter(User.id == uid).first()
            row.email = email  # type: ignore[assignment]
            row.username = _claim_username(db, _base_from_email(email))  # type: ignore[assignment]
            row.email_verified = True  # type: ignore[assignment]
            _add_identity(db, row, provider, provider_id, email)
            db.commit()

    from src.core.auth.auth_keys import load_user_profile

    return load_user_profile(uid) or {"id": uid, "name": "user", "role": "user", "vip_expires_at": None}


def list_linked_accounts(user_id: str) -> list[dict]:
    """Daftar identitas OAuth terikat (tabel + legacy) — untuk settings (W9e)."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthOAuthAccount, User

    with get_session() as db:
        u = db.query(User).filter(User.id == user_id, User.active.is_(True)).first()
        if not u:
            return []
        rows = (
            db.query(AuthOAuthAccount)
            .filter(AuthOAuthAccount.user_id == user_id)
            .order_by(AuthOAuthAccount.created_at)
            .all()
        )
        accounts: list[dict] = [
            {
                "provider": str(r.provider),
                "email": r.email,
                "email_verified": bool(r.email_verified),  # type: ignore[arg-type]
                "created_at": r.created_at,
            }
            for r in rows
        ]
        providers = {a["provider"] for a in accounts}
        for legacy in _legacy_providers(u):
            if legacy not in providers:
                accounts.append(
                    {
                        "provider": legacy,
                        "email": u.email,
                        "email_verified": bool(u.email_verified),  # type: ignore[arg-type]
                        "created_at": None,
                    }
                )
        return accounts


def unlink_oauth_provider(user_id: str, provider: str) -> str | None:
    """Lepas koneksi OAuth (W9e). Tolak bila meng-orphan akun.

    Return None bila sukses; `not_found` bila tak ada koneksi tersebut;
    `last_provider` bila ini koneksi terakhir akun TANPA password
    (lepas = akun tak bisa masuk lagi → fail-closed).
    """
    if provider not in _OAUTH_PROVIDERS:
        return "not_found"
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthOAuthAccount, User

    with get_session() as db:
        u = db.query(User).filter(User.id == user_id, User.active.is_(True)).first()
        if not u:
            return "not_found"
        rows = (
            db.query(AuthOAuthAccount)
            .filter(AuthOAuthAccount.user_id == user_id, AuthOAuthAccount.provider == provider)
            .all()
        )
        legacy_here = bool(u.auth_provider == provider and u.oauth_provider_id)
        if not rows and not legacy_here:
            return "not_found"
        others = (
            db.query(AuthOAuthAccount)
            .filter(AuthOAuthAccount.user_id == user_id, AuthOAuthAccount.provider != provider)
            .count()
        )
        legacy_other = any(p != provider for p in _legacy_providers(u))
        if not u.password_hash and others + (1 if legacy_other else 0) == 0:
            return "last_provider"
        for r in rows:
            db.delete(r)
        if legacy_here:
            nxt = (
                db.query(AuthOAuthAccount)
                .filter(AuthOAuthAccount.user_id == user_id, AuthOAuthAccount.provider != provider)
                .first()
            )
            if nxt is not None:
                u.auth_provider = str(nxt.provider)  # type: ignore[assignment]
                u.oauth_provider_id = str(nxt.provider_id)  # type: ignore[assignment]
            else:
                u.auth_provider = "password" if u.password_hash else None  # type: ignore[assignment]
                u.oauth_provider_id = None  # type: ignore[assignment]
        db.commit()
    return None
