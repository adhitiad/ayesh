"""Multi-user + API keys.

- users: id, name, key_hash (sha256), prefix (8 char awal, untuk identifikasi),
  active, created_at.
- Auth: header X-API-Key. Bila REQUIRE_API_KEY=1, /chat* wajib key valid (401).
  Bila mati (default), key opsional — request tanpa key jalan sebagai "default".
- Scope data: preferensi & proyek difilter per user via ContextVar current_user.
  Single-user lama otomatis jadi user "default" (kolom DEFAULT 'default').
"""

import hashlib
import secrets
from contextvars import ContextVar

current_user: ContextVar[str] = ContextVar("current_user", default="default")


def set_current_user(user_id: str) -> None:
    current_user.set(user_id or "default")


def get_current_user() -> str:
    return current_user.get() or "default"


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            prefix TEXT NOT NULL DEFAULT '',
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def _conn():
    from core.db import connect
    return connect()


def create_user(name: str) -> dict:
    """Buat user, return {id, name, api_key (plaintext, tampil SEKALI), prefix}."""
    name = (name or "").strip()[:100] or "tanpa-nama"
    api_key = f"fr_{secrets.token_hex(16)}"
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute(
        "INSERT INTO users(name, key_hash, prefix) VALUES (%s, %s, %s) RETURNING id;",
        (name, _hash_key(api_key), api_key[:11]),
    )
    uid = cur.fetchone()[0]
    conn.close()
    return {"id": uid, "name": name, "api_key": api_key, "prefix": api_key[:11]}


def verify_key(api_key: str) -> dict | None:
    """Return {id, name} bila key valid+aktif, else None."""
    if not api_key:
        return None
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT id, name FROM users WHERE key_hash = %s AND active = TRUE;",
                (_hash_key(api_key.strip()),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": str(row[0]), "name": row[1]}


def list_users() -> list:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT id, name, prefix, active FROM users ORDER BY id;")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "prefix": r[2], "active": r[3]} for r in rows]


def deactivate_user(uid: int) -> bool:
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
        return user["id"]
    if os.getenv("REQUIRE_API_KEY", "0") == "1":
        raise HTTPException(status_code=401, detail="X-API-Key tidak valid. Buat via POST /users.")
    set_current_user("default")
    return "default"
