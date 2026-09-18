"""Koneksi database terpusat (pengganti boilerplate psycopg2 di tiap modul)."""

from dotenv import load_dotenv

load_dotenv()


def database_url() -> str:
    from config.routing_keywords_pg import DATABASE_URL
    return DATABASE_URL


def connect():
    """Koneksi psycopg2 autocommit. Caller wajib .close()."""
    import psycopg2
    conn = psycopg2.connect(database_url())
    conn.autocommit = True
    return conn
