"""Multi-user + API keys with RBAC.

- users: id, name, key_hash (sha256), prefix (8 char awal, untuk identifikasi),
  role (owner|admin|user), active, created_at.
- Auth: header X-API-Key. Bila REQUIRE_API_KEY=1, /chat* wajib key valid (401).
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


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            prefix TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('owner','admin','user')),
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    # Migration: add role column if it doesn't exist
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'role'
            ) THEN
                ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('owner','admin','user'));
            END IF;
        END $$;
    """)
    # Migration: alter id column from SERIAL to TEXT if needed
    cur.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'id'
                AND data_type != 'text'
            ) THEN
                ALTER TABLE users ALTER COLUMN id TYPE TEXT USING id::TEXT;
            END IF;
        END $$;
    """)


def _conn():
    from src.core.db import connect

    return connect()


def create_user(name: str, role: str = "user") -> dict:
    """Buat user, return {id, name, api_key (plaintext, tampil SEKALI), prefix, role}."""
    name = (name or "").strip()[:100] or "tanpa-nama"
    role = (role or "user").lower()
    if role not in ("owner", "admin", "user"):
        role = "user"
    api_key = f"fr_{secrets.token_hex(16)}"
    uid = str(uuid.uuid4())
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute(
        "INSERT INTO users(id, name, key_hash, prefix, role) VALUES (%s, %s, %s, %s, %s) RETURNING id;",
        (uid, name, _hash_key(api_key), api_key[:11], role),
    )
    fetched = cur.fetchone()
    conn.close()
    return {
        "id": fetched[0] if fetched else uid,
        "name": name,
        "api_key": api_key,
        "prefix": api_key[:11],
        "role": role,
    }


def verify_key(api_key: str) -> dict | None:
    """Return {id, name, role} bila key valid+aktif, else None."""
    if not api_key:
        return None
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute(
        "SELECT id, name, role FROM users WHERE key_hash = %s AND active = TRUE;",
        (_hash_key(api_key.strip()),),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": str(row[0]), "name": row[1], "role": row[2]}


def list_users() -> list:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT id, name, prefix, role, active FROM users ORDER BY id;")
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "prefix": r[2], "role": r[3], "active": r[4]}
        for r in rows
    ]


def deactivate_user(uid: str) -> bool:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute("UPDATE users SET active = FALSE WHERE id = %s;", (uid,))
    n = cur.rowcount
    conn.close()
    return n > 0


def bind_request_user(request) -> str:
    """Baca X-API-Key, set ContextVar, return user_id. Raise 401 bila wajib & invalid."""
    import os
    from fastapi import HTTPException

    key = (request.headers.get("X-API-Key") or "").strip()
    user = verify_key(key) if key else None
    if user:
        set_current_user(user["id"])
        set_current_user_role(user.get("role", "user"))
        return user["id"]
    if os.getenv("REQUIRE_API_KEY", "1") == "1":
        raise HTTPException(
            status_code=401, detail="X-API-Key tidak valid. Buat via POST /users."
        )
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
        raise HTTPException(
            status_code=403, detail="Forbidden: admin or owner role required"
        )
    return user_id


def require_owner_only(request: Request) -> str:
    """Require owner role ONLY (not admin). Returns user_id. Raises 403 if not owner."""
    user_id = require_auth(request)
    role = get_current_user_role()
    if role != "owner":
        raise HTTPException(status_code=403, detail="Forbidden: owner role required")
    return user_id


def bootstrap_owner() -> dict | None:
    """Create initial owner user if no owner exists. Returns user dict or None.

    Bootstrap mechanism: only works when the users table is empty.
    The owner key is printed to stdout for the operator to save.
    """
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'owner' AND active = TRUE;")
    count = cur.fetchone()[0]
    conn.close()
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
