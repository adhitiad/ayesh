"""Request binding: extract credential (API key atau session cookie) → ContextVars."""

import os

from fastapi import HTTPException, Request

from src.core.auth.auth_context import (
    _authenticated,
    set_current_user,
    set_current_user_role,
    set_current_user_vip_expires,
)
from src.core.auth.auth_keys import load_user_profile, verify_key


def _bind(user: dict | None) -> str | None:
    if not user:
        return None
    _authenticated.set(True)
    set_current_user(user["id"])
    set_current_user_role(user.get("role", "user"))
    set_current_user_vip_expires(user.get("vip_expires_at"))
    return user["id"]


def _api_key_user(request: Request) -> dict | None:
    key = (request.headers.get("X-API-Key") or "").strip()
    if not key:
        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.startswith("Bearer "):
            key = auth_header[7:].strip()
    return verify_key(key) if key else None


def _session_user(request: Request) -> dict | None:
    from src.core.auth.sessions import read_session_token, verify_session

    token = read_session_token(request)
    if not token:
        return None
    try:
        info = verify_session(token)
    except Exception:
        return None  # fail-closed: error DB ≠ authenticate
    if not info:
        return None
    return load_user_profile(info["user_id"])


def bind_request_user(request: Request) -> str:
    """Set ContextVar dari API key (prefer) atau session cookie; return user_id.

    Raise 401 bila wajib (REQUIRE_API_KEY=1) dan tidak ada kredensial valid.
    """
    user = _api_key_user(request) or _session_user(request)
    if user:
        return _bind(user)
    if os.getenv("REQUIRE_API_KEY", "1") == "1":
        raise HTTPException(status_code=401, detail="X-API-Key atau sesi tidak valid. Buat via POST /users atau login.")
    _authenticated.set(False)
    set_current_user("default")
    set_current_user_role("user")
    set_current_user_vip_expires(None)
    return "default"
