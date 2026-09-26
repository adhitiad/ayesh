"""OAuth2 Authorization Code (Google, GitHub) via httpx.

State+nonce disimpan di auth_oauth_states (sekali-pakai, TTL). Exchange &
userinfo langsung ke provider endpoint — tidak ada library OAuth pihak ketiga,
kontrol penuh atas scope & anti-SSRF (URL provider fixed).
"""

import logging
import os
import secrets
import urllib.parse
from datetime import timedelta

import httpx

from src.core.auth.auth_context import _utcnow
from src.core.auth.auth_db import _ensure_auth_tables

PROVIDERS = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",  # nosec B105 - endpoint OAuth, bukan kredensial
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "github": {
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",  # nosec B105 - endpoint OAuth, bukan kredensial
        "userinfo": "https://api.github.com/user",
        "emails": "https://api.github.com/user/emails",
        "scope": "read:user user:email",
    },
}

logger = logging.getLogger(__name__)


def _client_id(provider: str) -> str:
    return os.getenv(f"AUTH_OAUTH_{provider.upper()}_CLIENT_ID", "")


def _client_secret(provider: str) -> str:
    return os.getenv(f"AUTH_OAUTH_{provider.upper()}_CLIENT_SECRET", "")


def is_provider_enabled(provider: str) -> bool:
    return provider in PROVIDERS and bool(_client_id(provider)) and bool(_client_secret(provider))


def _callback_url(provider: str) -> str:
    base = os.getenv("AUTH_OAUTH_BASE_URL", os.getenv("PUBLIC_API_BASE_URL", "http://localhost:8080")).rstrip("/")
    return f"{base}/auth/oauth/{provider}/callback"


def _state_ttl_minutes() -> int:
    return int(os.getenv("AUTH_OAUTH_STATE_TTL_MIN", "10"))


def start_oauth(provider: str, redirect_to: str | None = None) -> dict:
    """Buat authorize URL + simpan state. Raise ValueError bila provider off."""
    if provider not in PROVIDERS:
        raise ValueError(f"provider OAuth tidak dikenal: {provider}")
    if not is_provider_enabled(provider):
        raise ValueError(f"OAuth {provider} tidak dikonfigurasi (AUTH_OAUTH_{provider.upper()}_CLIENT_* kosong)")
    _ensure_auth_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthOAuthState

    state = secrets.token_urlsafe(32)
    now = _utcnow()
    with get_session() as db:
        db.add(
            AuthOAuthState(
                state=state,
                provider=provider,
                redirect_to=(redirect_to or "")[:500] or None,
                created_at=now,
                expires_at=now + timedelta(minutes=_state_ttl_minutes()),
            )
        )
        db.commit()

    cfg = PROVIDERS[provider]
    params = {
        "client_id": _client_id(provider),
        "redirect_uri": _callback_url(provider),
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    url = f"{cfg['authorize']}?{urllib.parse.urlencode(params)}"
    return {"provider": provider, "state": state, "authorize_url": url}


async def _exchange_code(provider: str, code: str) -> dict:
    cfg = PROVIDERS[provider]
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            cfg["token"],
            data={
                "client_id": _client_id(provider),
                "client_secret": _client_secret(provider),
                "redirect_uri": _callback_url(provider),
                "grant_type": "authorization_code",
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


async def exchange_oauth(provider: str, code: str, state: str) -> tuple[str | None, dict]:
    """Tukar code + validasi state sekali-pakai.

    Return (redirect_to, profile); profile = {provider, provider_user_id,
    email, name, email_verified}. Raise ValueError / httpx.HTTPError bila gagal.
    """
    _ensure_auth_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import AuthOAuthState

    redirect_to: str | None = None
    with get_session() as db:
        row = db.query(AuthOAuthState).filter(AuthOAuthState.state == state).first()
        if not row or row.provider != provider:
            raise ValueError("state OAuth tidak valid atau sudah terpakai")
        now = _utcnow()
        try:
            expired = row.expires_at <= now
        except Exception:
            expired = True
        if expired:
            raise ValueError("state OAuth kedaluwarsa")
        redirect_to = row.redirect_to
        db.delete(row)
        db.commit()

    token_data = await _exchange_code(provider, code)
    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError("provider tidak mengembalikan access_token")

    cfg = PROVIDERS[provider]
    async with httpx.AsyncClient(timeout=15) as client:
        user_resp = await client.get(
            cfg["userinfo"], headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        )
        user_resp.raise_for_status()
        info = user_resp.json()

    if provider == "google":
        provider_user_id = str(info.get("sub", ""))
        email = (info.get("email") or "").strip().lower()
        email_verified = bool(info.get("email_verified"))
        name = (info.get("name") or "").strip() or (info.get("given_name") or "")
    else:
        provider_user_id = str(info.get("id", ""))
        email = (info.get("email") or "").strip().lower()
        email_verified = True
        name = (info.get("name") or "").strip() or (info.get("login") or "")
        if not email:
            emails_resp = await client.get(cfg["emails"], headers={"Authorization": f"Bearer {access_token}"})
            if emails_resp.status_code == 200:
                for entry in emails_resp.json():
                    if entry.get("primary"):
                        email = (entry.get("email") or "").strip().lower()
                        email_verified = bool(entry.get("verified"))
                        break

    if not provider_user_id:
        raise ValueError(f"provider {provider} tidak mengembalikan identity")

    return (
        redirect_to,
        {
            "provider": provider,
            "provider_user_id": provider_user_id,
            "email": email,
            "name": name[:100] or "user",
            "email_verified": bool(email_verified),
        },
    )
