"""Web session (httpOnly cookie) + CSRF double-submit.

Session token: `ayss_<random>` disimpan hashed (sha256) di auth_sessions.
Cookie `ayesh_session` (HttpOnly, SameSite=Lax, Secure bila AUTH_COOKIE_SECURE=1)
+ cookie `ayesh_csrf` (double-submit; dibaca JS untuk header X-CSRF-Token).
"""

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import timedelta

from src.core.auth.auth_context import _utcnow
from src.core.auth.auth_db import _ensure_auth_columns, _ensure_auth_tables

SESSION_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "ayesh_session")
CSRF_COOKIE_NAME = "ayesh_csrf"

_isolation_checked = False


def _ensure():
    """Lazy ensure: kolom auth + tabel sesi (sekali per proses)."""
    _ensure_auth_columns()
    _ensure_auth_tables()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_ttl_hours() -> int:
    return int(os.getenv("AUTH_SESSION_TTL_HOURS", "168"))


def _cookie_secure() -> bool:
    return os.getenv("AUTH_COOKIE_SECURE", "0") == "1"


def _cookie_samesite() -> str:
    value = os.getenv("AUTH_COOKIE_SAMESITE", "lax").lower()
    if value not in ("lax", "strict", "none"):
        return "lax"
    return value


def create_session(
    user_id: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Buat sesi baru. Return {id, session_token, expires_at} (token SEKALI)."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthSession

    token = f"ayss_{secrets.token_urlsafe(32)}"
    now = _utcnow()
    expires_at = now + timedelta(hours=_session_ttl_hours())
    row_id = str(uuid.uuid4())
    with get_session() as db:
        db.add(
            AuthSession(
                id=row_id,
                user_id=user_id,
                token_hash=_hash(token),
                ip=(ip or "")[:64] or None,
                user_agent=(user_agent or "")[:512] or None,
                created_at=now,
                expires_at=expires_at,
                last_active_at=now,
            )
        )
        db.commit()
    return {"id": row_id, "session_token": token, "expires_at": expires_at}


def verify_session(token: str | None) -> dict | None:
    """Validasi sesi: hash cocok, belum revoked/expired. Slide last_active_at.

    Return {id, user_id, expires_at} atau None. Gagal karena DB error diasumsikan
    deny (fail-closed), namun disemangati current code (auth_keys) error dicatat.
    """
    if not token:
        return None
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthSession

    with get_session() as db:
        row = db.query(AuthSession).filter(AuthSession.token_hash == _hash(token)).first()
        if not row:
            return None
        if row.revoked_at is not None:
            return None
        now = _utcnow()
        expires = row.expires_at
        try:
            expired = expires <= now
        except Exception:
            expired = True
        if expired:
            return None
        row.last_active_at = now  # type: ignore[assignment]
        db.commit()
        return {"id": str(row.id), "user_id": str(row.user_id), "expires_at": expires}


def revoke_session(token: str | None) -> bool:
    if not token:
        return False
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthSession

    with get_session() as db:
        row = db.query(AuthSession).filter(AuthSession.token_hash == _hash(token)).first()
        if not row or row.revoked_at is not None:
            return False
        row.revoked_at = _utcnow()  # type: ignore[assignment]
        db.commit()
        return True


def revoke_all_user_sessions(user_id: str, keep_token: str | None = None) -> int:
    """Revoke semua sesi user (dipakai saat ganti password / reset)."""
    _ensure()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthSession

    keep_hash = _hash(keep_token) if keep_token else None
    now = _utcnow()
    with get_session() as db:
        rows = db.query(AuthSession).filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)).all()
        count = 0
        for row in rows:
            if keep_hash and row.token_hash == keep_hash:
                continue
            row.revoked_at = now  # type: ignore[assignment]
            count += 1
        db.commit()
        return count


# ── Cookie helpers ─────────────────────────────────────────────────────


def read_session_token(request) -> str | None:
    return (request.cookies.get(SESSION_COOKIE_NAME) or "").strip() or None


def _cookie_attrs(http_only: bool) -> dict:
    return {
        "path": "/",
        "httponly": http_only,
        "secure": _cookie_secure(),
        "samesite": _cookie_samesite(),
        "max_age": _session_ttl_hours() * 3600,
    }


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE_NAME, token, **_cookie_attrs(http_only=True))
    # CSRF double-submit: cookie tanpa HttpOnly (JS baca utk header) + token baru.
    csrf = secrets.token_hex(32)
    response.set_cookie(CSRF_COOKIE_NAME, csrf, **_cookie_attrs(http_only=False))


def clear_session_cookies(response) -> None:
    for name in (SESSION_COOKIE_NAME, CSRF_COOKIE_NAME):
        response.delete_cookie(name, path="/")


def verify_csrf(request) -> bool:
    """Double-submit: header X-CSRF-Token harus sama dgn cookie ayesh_csrf."""
    cookie = request.cookies.get(CSRF_COOKIE_NAME) or ""
    header = request.headers.get("X-CSRF-Token") or ""
    if not cookie or not header:
        return False
    return hmac.compare_digest(cookie, header)
