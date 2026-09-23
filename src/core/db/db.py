"""Koneksi database terpusat (pengganti boilerplate psycopg2 di tiap modul)."""

from dotenv import load_dotenv

load_dotenv()


def database_url() -> str:
    from src.config.routing_keywords_pg import DATABASE_URL

    return DATABASE_URL or ""


def connect(*, autocommit: bool = True):
    """Koneksi psycopg2. Caller wajib .close().

    autocommit=True (default) — tiap statement langsung commit (legacy mode).
    autocommit=False — caller wajib commit/rollback secara eksplisit.
    """
    import psycopg2

    conn = psycopg2.connect(database_url())
    conn.autocommit = autocommit
    return conn
