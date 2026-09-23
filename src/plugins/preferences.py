"""User preferences: ingat_preferensi, lihat_preferensi, get_preferences_block."""

import logging

from langchain_core.tools import tool

from src.plugins.tool_error import tool_error_from_exception


def _pref_user() -> str:
    """Get current user for preference scoping. Never returns 'default'."""
    try:
        from src.core.auth.auth import get_current_user

        uid = get_current_user()
        if uid and uid != "default":
            return uid
    except Exception as _e:
        logging.getLogger(__name__).debug("_pref_user error: %s", _e)
    return "anonymous"


def _pref_ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS preferensi (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.execute("ALTER TABLE preferensi ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT 'default';")
    cur.execute("UPDATE preferensi SET user_id = 'default' WHERE user_id IS NULL;")
    cur.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'preferensi_pkey') THEN
                ALTER TABLE preferensi DROP CONSTRAINT preferensi_pkey;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'preferensi_user_pkey') THEN
                ALTER TABLE preferensi ADD CONSTRAINT preferensi_user_pkey PRIMARY KEY (user_id, key);
            END IF;
        END $$;
    """)


def get_preferences_block() -> str:
    """Blok teks preferensi user untuk injeksi prompt. Kosong bila belum ada."""
    try:
        import psycopg2

        from src.config.routing_keywords_pg import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        try:
            cur = conn.cursor()
            _pref_ensure_table(cur)
            conn.commit()
            cur.execute(
                "SELECT key, value FROM preferensi WHERE user_id = %s ORDER BY key;",
                (_pref_user(),),
            )
            rows = cur.fetchall()
            if not rows:
                return ""
            lines = ["Preferensi user yang tersimpan:"]
            lines += [f"- {k}: {v}" for k, v in rows]
            return "\n".join(lines)
        finally:
            conn.close()
    except Exception as _e:
        logging.getLogger(__name__).debug("get_preferences_block error: %s", _e)
        return ""


@tool
def ingat_preferensi(key: str, value: str) -> str:
    """Simpan preferensi/fakta tentang user lintas session (nama, kesukaan, setting).

    Pakai saat user menyatakan sesuatu yang layak diingat jangka panjang.
    JANGAN untuk info sesaat atau rahasia (password, token, OTP).

    Args:
        key: Kunci singkat lowercase. Contoh: "nama", "bahasa", "framework".
        value: Nilai preferensi. Contoh: "Budi", "python".
    """
    try:
        import psycopg2

        from src.config.routing_keywords_pg import DATABASE_URL

        key = key.strip().lower().replace(" ", "_")[:50]
        value = value.strip()[:500]
        if not key or not value:
            return "Error: key dan value tidak boleh kosong."
        conn = psycopg2.connect(DATABASE_URL)
        try:
            cur = conn.cursor()
            _pref_ensure_table(cur)
            cur.execute(
                "UPDATE preferensi SET value = %s, updated_at = NOW() WHERE user_id = %s AND key = %s;",
                (value, _pref_user(), key),
            )
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT INTO preferensi(key, value, user_id) VALUES (%s, %s, %s);",
                    (key, value, _pref_user()),
                )
            conn.commit()
            return f"Preferensi tersimpan: {key} = {value}"
        finally:
            conn.close()
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def lihat_preferensi() -> str:
    """Lihat semua preferensi user yang tersimpan lintas session."""
    block = get_preferences_block()
    return block or "Belum ada preferensi tersimpan."
