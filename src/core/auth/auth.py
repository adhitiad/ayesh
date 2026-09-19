"""Multi-user + API keys with RBAC.

- users: id, name, key_hash (sha256), prefix (8 char awal, untuk identifikasi),
  role (owner|admin|user), active, created_at.
- Auth: header X-API-Key atau Authorization: Bearer. Bila REQUIRE_API_KEY=1, /chat* wajib key valid (401).
  Bila mati (default), key opsional — request tanpa key jalan sebagai "default".
- Scope data: preferensi & proyek difilter per user via ContextVar current_user.
  Single-user lama otomatis jadi user "default" (kolom DEFAULT 'default').
- RBAC roles:
  owner: users, jobs, approvals, logs, audit, analytics, system configuration
  admin: operational endpoints (tasks, sessions, memory, chat)
  user: chat, own sessions, own memory, own tasks
"""

import hashlib
import secrets
import uuid
from contextvars import ContextVar

from fastapi import HTTPException, Request

current_user: ContextVar[str] = ContextVar("current_user", default="default")
current_user_role: ContextVar[str] = ContextVar("current_user_role", default="user")


def set_current_user(user_id: str) -> None:
    current_user.set(user_id or "default")


def get_current_user() -> str:
    return current_user.get() or "default"


def set_current_user_role(role: str) -> None:
    current_user_role.set(role or "user")


def get_current_user_role() -> str:
    return current_user_role.get() or "user"


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _ensure_table(cur=None):
    """Ensure users table exists. Accepts cursor (no-op) for backward compat."""
    from src.core.db.db_engine import get_engine
    from src.core.db.models import Base, User

    Base.metadata.create_all(get_engine(), tables=[User.__table__])


def create_user(name: str, role: str = "user") -> dict:
    """Buat user, return {id, name, api_key (plaintext, tampil SEKALI), prefix, role}."""
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine
    from src.core.db.models import User

    name = (name or "").strip()[:100] or "tanpa-nama"
    role = (role or "user").lower()
    if role not in ("owner", "admin", "user"):
        role = "user"
    api_key = f"fr_{secrets.token_hex(16)}"
    uid = str(uuid.uuid4())

    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        user = User(
            id=uid,
            name=name,
            key_hash=_hash_key(api_key),
            prefix=api_key[:11],
            role=role,
            active=True,
        )
        db.add(user)
        db.commit()
    return {
        "id": uid,
        "name": name,
        "api_key": api_key,
        "prefix": api_key[:11],
        "role": role,
    }


def verify_key(api_key: str) -> dict | None:
    """Return {id, name, role} bila key valid+aktif, else None."""
    if not api_key:
        return None
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine
    from src.core.db.models import User

    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        user = db.query(User).filter(User.key_hash == _hash_key(api_key.strip()), User.active.is_(True)).first()
        if not user:
            return None
        return {"id": str(user.id), "name": user.name, "role": user.role}


def list_users() -> list:
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine
    from src.core.db.models import User

    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        users = db.query(User).order_by(User.id).all()
        return [{"id": u.id, "name": u.name, "prefix": u.prefix, "role": u.role, "active": u.active} for u in users]


def deactivate_user(uid: str) -> bool:
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine
    from src.core.db.models import User

    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            return False
        user.active = False
        db.commit()
        return True


def bind_request_user(request) -> str:
    """Baca X-API-Key atau Authorization: Bearer, set ContextVar, return user_id. Raise 401 bila wajib & invalid."""
    import os

    # Support both X-API-Key and Authorization: Bearer
    key = (request.headers.get("X-API-Key") or "").strip()
    if not key:
        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.startswith("Bearer "):
            key = auth_header[7:].strip()
    user = verify_key(key) if key else None
    if user:
        set_current_user(user["id"])
        set_current_user_role(user.get("role", "user"))
        return user["id"]
    if os.getenv("REQUIRE_API_KEY", "1") == "1":
        raise HTTPException(status_code=401, detail="X-API-Key tidak valid. Buat via POST /users.")
    set_current_user("default")
    set_current_user_role("user")
    return "default"


# === Centralized Authorization Helpers ===


def require_auth(request: Request) -> str:
    """Require valid authentication. Returns user_id. Raises 401 if not authenticated."""
    import os

    user_id = bind_request_user(request)
    if user_id == "default" and os.getenv("REQUIRE_API_KEY", "1") == "1":
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def require_owner(request: Request, resource_owner_id: str) -> str:
    """Require that the authenticated user owns the resource. Returns user_id. Raises 403 if not owner."""
    user_id = require_auth(request)
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
    user_id = require_auth(request)
    role = get_current_user_role()
    if role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Forbidden: admin or owner role required")
    return user_id


def require_owner_only(request: Request) -> str:
    """Require owner role ONLY (not admin). Returns user_id. Raises 403 if not owner."""
    user_id = require_auth(request)
    role = get_current_user_role()
    if role != "owner":
        raise HTTPException(status_code=403, detail="Forbidden: owner role required")
    return user_id


def bootstrap_owner() -> dict | None:
    """Create initial owner user if no owner exists. Returns user dict or None."""
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine
    from src.core.db.models import User

    _ensure_table()
    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        count = db.query(User).filter(User.role == "owner", User.active.is_(True)).count()
        if count > 0:
            return None
    return create_user("bootstrap-owner", "owner")


def require_owner_or_admin(request: Request, resource_owner_id: str) -> str:
    """Require owner of resource OR admin/owner role. Returns user_id. Raises 403 if neither."""
    user_id = require_auth(request)
    role = get_current_user_role()
    if role in ("admin", "owner"):
        return user_id
    if user_id != resource_owner_id:
        raise HTTPException(status_code=403, detail="Forbidden: not resource owner")
    return user_id


def get_current_user_id() -> str:
    """Get current authenticated user_id from ContextVar."""
    return get_current_user()
