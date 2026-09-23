"""Authorization guards: require_auth, require_owner, require_admin, etc."""

from fastapi import HTTPException, Request

from src.core.auth.auth_context import (
    get_current_user_role,
    is_authenticated,
)
from src.core.auth.auth_request import bind_request_user


def require_auth(request: Request) -> str:
    """Require valid authentication. Returns user_id. Raises 401 if not authenticated."""
    import os

    user_id = bind_request_user(request)
    if user_id == "default" and os.getenv("REQUIRE_API_KEY", "1") == "1":
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def effective_auth_config() -> dict:
    """Ringkasan konfigurasi auth effective (log startup & introspeksi, vuln-0002).

    Default fail-closed: REQUIRE_API_KEY tidak diset → auth aktif ("1").
    """
    import os

    raw = os.getenv("REQUIRE_API_KEY", "1")
    return {
        "require_api_key": raw == "1",
        "require_api_key_raw": raw,
        "control_plane": "authenticated-only (require_authenticated, selalu fail-closed)",
        "default": "fail-closed (tanpa env → auth aktif)",
    }


def require_authenticated(request: Request) -> str:
    """Require a VALID API key; fails closed even when REQUIRE_API_KEY=0.

    Endpoint control-plane (jobs, tasks, approvals, sessions, memory) wajib
    terautentikasi. Mode REQUIRE_API_KEY=0 hanya membuka chat/metadata publik,
    bukan control-plane. Fail-closed: anonim selalu ditolak di sini.
    """
    user_id = bind_request_user(request)
    if not is_authenticated():
        raise HTTPException(
            status_code=401,
            detail="API key valid diperlukan untuk endpoint control-plane (fail-closed; REQUIRE_API_KEY=0 tidak menonaktifkan auth).",
        )
    return user_id


def require_owner(request: Request, resource_owner_id: str) -> str:
    """Require that the authenticated user owns the resource. Returns user_id. Raises 403 if not owner."""
    user_id = require_authenticated(request)
    role = get_current_user_role()
    # Owner role can access any resource
    if role == "owner":
        return user_id
    # Users can only access their own resources
    if user_id != resource_owner_id:
        raise HTTPException(status_code=403, detail="Forbidden: not resource owner")
    return user_id


def require_admin(request: Request) -> str:
    """Require admin or owner role. Returns user_id. Raises 403 if insufficient privileges."""
    user_id = require_authenticated(request)
    role = get_current_user_role()
    if role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Forbidden: admin or owner role required")
    return user_id


def require_owner_only(request: Request) -> str:
    """Require owner role ONLY (not admin). Returns user_id. Raises 403 if not owner."""
    user_id = require_authenticated(request)
    role = get_current_user_role()
    if role != "owner":
        raise HTTPException(status_code=403, detail="Forbidden: owner role required")
    return user_id


def bootstrap_owner() -> dict | None:
    """Create initial owner user if no owner exists. Returns user dict or None."""

    from src.core.auth.auth_keys import _ensure_rotation_columns, _ensure_table, create_user
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    _ensure_rotation_columns()
    _ensure_table()
    with get_session() as db:
        count = db.query(User).filter(User.role == "owner", User.active.is_(True)).count()
        if count > 0:
            return None
    return create_user("bootstrap-owner", "owner")


def require_owner_or_admin(request: Request, resource_owner_id: str) -> str:
    """Require owner of resource OR admin/owner role. Returns user_id. Raises 403 if neither."""
    user_id = require_authenticated(request)
    role = get_current_user_role()
    if role in ("admin", "owner"):
        return user_id
    if user_id != resource_owner_id:
        raise HTTPException(status_code=403, detail="Forbidden: not resource owner")
    return user_id
