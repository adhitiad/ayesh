"""Request binding: extract API key from request, verify, set ContextVars."""

import os

from fastapi import HTTPException, Request

from src.core.auth.auth_context import (
    _authenticated,
    set_current_user,
    set_current_user_role,
    set_current_user_vip_expires,
)
from src.core.auth.auth_keys import verify_key


def bind_request_user(request: Request) -> str:
    """Baca X-API-Key atau Authorization: Bearer, set ContextVar, return user_id. Raise 401 bila wajib & invalid."""
    # Support both X-API-Key and Authorization: Bearer
    key = (request.headers.get("X-API-Key") or "").strip()
    if not key:
        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.startswith("Bearer "):
            key = auth_header[7:].strip()
    user = verify_key(key) if key else None
    if user:
        _authenticated.set(True)
        set_current_user(user["id"])
        set_current_user_role(user.get("role", "user"))
        set_current_user_vip_expires(user.get("vip_expires_at"))
        return user["id"]
    if os.getenv("REQUIRE_API_KEY", "1") == "1":
        raise HTTPException(status_code=401, detail="X-API-Key tidak valid. Buat via POST /users.")
    _authenticated.set(False)
    set_current_user("default")
    set_current_user_role("user")
    set_current_user_vip_expires(None)
    return "default"
