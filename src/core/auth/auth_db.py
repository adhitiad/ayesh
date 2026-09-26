"""Lazy migration tabel auth manusia (email/OAuth/2FA).

Tabel users tidak dikelola Alembic; kolom auth ditambahkan in-place lewat
ALTER TABLE (sekali per proses, thread-safe), menyusul pola _ensure_* di
auth_keys.py. Tabel baru (auth_sessions, auth_oauth_states, auth_tokens,
auth_oauth_accounts) dibuat via Base.metadata.create_all + backfill identitas
legacy → auth_oauth_accounts. Kegagalan tidak ditelan diam-diam.
"""

import logging
import threading

_AUTH_COLUMNS = {
    "email": "VARCHAR(255)",
    "username": "VARCHAR(50)",  # alias login (nullable; unik case-insensitive, W9a)
    "password_hash": "VARCHAR(512)",  # nosec B105 - nama kolom DB, bukan kredensial
    "email_verified": "BOOLEAN NOT NULL DEFAULT false",
    "auth_provider": "VARCHAR(30)",
    "oauth_provider_id": "VARCHAR(255)",
    "totp_secret": "VARCHAR(64)",  # nosec B105 - nama kolom DB (TOTP secret terenkripsi at-rest)
    "totp_confirmed_at": "TIMESTAMP",
    "totp_backup_hashes": "TEXT",
}

_auth_columns_ensured = False
_auth_columns_lock = threading.Lock()
_auth_tables_ensured = False
_auth_tables_lock = threading.Lock()


def _ensure_auth_columns():
    """Tambah kolom auth di tabel users bila belum ada + unique index email/username."""
    global _auth_columns_ensured
    if _auth_columns_ensured:
        return
    with _auth_columns_lock:
        if _auth_columns_ensured:
            return
        try:
            from sqlalchemy import inspect, text

            from src.core.db.db_engine import get_engine

            engine = get_engine()
            cols = {c["name"] for c in inspect(engine).get_columns("users")}
            missing = [n for n in _AUTH_COLUMNS if n not in cols]
            if missing:
                with engine.begin() as conn:
                    for name in missing:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {_AUTH_COLUMNS[name]}"))
            # email unik — index unik (NULL ganda diizinkan, PG memperlakukan
            # NULL berbeda-beda sehingga user tanpa email tidak bertabrakan).
            if "email" in cols or "email" not in missing:
                with engine.begin() as conn:
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"))
            # username unik case-insensitive (lower) — banyak baris NULL diizinkan
            # (akun API-key lama tanpa alias tidak saling bertabrakan).
            with engine.begin() as conn:
                conn.execute(
                    text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username_lower ON users (lower(username))")
                )
        except Exception:
            logging.getLogger(__name__).exception("Gagal migrasi kolom auth di tabel users")
        finally:
            _auth_columns_ensured = True


def backfill_oauth_accounts() -> int:
    """Salin identitas legacy (users.auth_provider/oauth_provider_id) → auth_oauth_accounts.

    Idempoten (NOT EXISTS + ON CONFLICT DO NOTHING). Dipanggil sekali dari
    _ensure_auth_tables; bisa dipanggil ulang (mis. tes). Return baris tersalin.
    """
    from sqlalchemy import text

    from src.core.db.db_engine import get_engine

    with get_engine().begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO auth_oauth_accounts
                    (id, user_id, provider, provider_id, email, email_verified, created_at)
                SELECT gen_random_uuid()::text, u.id, u.auth_provider, u.oauth_provider_id, u.email, u.email_verified, NOW()
                FROM users u
                WHERE u.auth_provider IN ('google', 'github')
                  AND u.oauth_provider_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM auth_oauth_accounts a
                      WHERE a.user_id = u.id
                        AND a.provider = u.auth_provider
                        AND a.provider_id = u.oauth_provider_id
                  )
                ON CONFLICT DO NOTHING
                """
            )
        )
        return int(result.rowcount or 0)


def _ensure_auth_tables():
    """Buat tabel auth_sessions, auth_oauth_states, auth_tokens, auth_oauth_accounts."""
    global _auth_tables_ensured
    if _auth_tables_ensured:
        return
    with _auth_tables_lock:
        if _auth_tables_ensured:
            return
        try:
            from src.core.db.db_engine import get_engine
            from src.core.db.models import AuthOAuthAccount, AuthOAuthState, AuthSession, AuthToken, Base

            Base.metadata.create_all(
                get_engine(),
                tables=[
                    AuthSession.__table__,
                    AuthOAuthState.__table__,
                    AuthToken.__table__,
                    AuthOAuthAccount.__table__,
                ],
            )
            backfill_oauth_accounts()
        except Exception:
            logging.getLogger(__name__).exception("Gagal migrasi tabel auth")
        finally:
            _auth_tables_ensured = True
