"""User projects: simpan_proyek, catat_proyek, lihat_proyek, get_projects_block."""

import logging

from langchain_core.tools import tool

from src.plugins.tool_error import tool_error_from_exception


def _proj_user() -> str:
    """Get current user for project scoping. Never returns 'default'."""
    try:
        from src.core.auth.auth import get_current_user

        uid = get_current_user()
        if uid and uid != "default":
            return uid
    except Exception as _e:
        logging.getLogger(__name__).debug("_proj_user error: %s", _e)
    return "anonymous"


def _proj_ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS proyek (
            nama TEXT PRIMARY KEY,
            goal TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'aktif',
            catatan TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.execute("ALTER TABLE proyek ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT 'default';")
    cur.execute("UPDATE proyek SET user_id = 'default' WHERE user_id IS NULL;")
    cur.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'proyek_pkey') THEN
                ALTER TABLE proyek DROP CONSTRAINT proyek_pkey;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'proyek_user_pkey') THEN
                ALTER TABLE proyek ADD CONSTRAINT proyek_user_pkey PRIMARY KEY (user_id, nama);
            END IF;
        END $$;
    """)


def get_projects_block() -> str:
    """Blok proyek aktif untuk injeksi prompt. Kosong bila belum ada."""
    try:
        import psycopg2

        from src.config.routing_keywords_pg import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        try:
            cur = conn.cursor()
            _proj_ensure_table(cur)
            conn.commit()
            cur.execute(
                "SELECT nama, goal, status, catatan FROM proyek WHERE user_id = %s AND status <> 'selesai' ORDER BY updated_at DESC;",
                (_proj_user(),),
            )
            rows = cur.fetchall()
            if not rows:
                return ""
            lines = ["Proyek aktif yang sedang dikerjakan user:"]
            for nama, goal, status, catatan in rows:
                line = f"- {nama} [{status}]: {goal}"
                if catatan:
                    line += f" | Catatan: {catatan[:300]}"
                lines.append(line)
            return "\n".join(lines)
        finally:
            conn.close()
    except Exception as _e:
        logging.getLogger(__name__).debug("get_projects_block error: %s", _e)
        return ""


@tool
def simpan_proyek(nama: str, goal: str, status: str = "aktif") -> str:
    """Simpan/perbarui proyek jangka panjang user (tujuan, status, lintas session).

    Pakai saat user memulai pekerjaan multi-session (skripsi, renovasi, bisnis).
    JANGAN untuk tugas sekali-jawab.

    Args:
        nama: Nama pendek proyek. Contoh: "renovasi-dapur".
        goal: Tujuan proyek dalam 1-2 kalimat.
        status: aktif / jeda / selesai.
    """
    try:
        import psycopg2

        from src.config.routing_keywords_pg import DATABASE_URL

        nama = nama.strip().lower().replace(" ", "-")[:60]
        status = status.strip().lower()[:20]
        if status not in ("aktif", "jeda", "selesai"):
            return "Error: status harus aktif/jeda/selesai."
        if not nama or not goal.strip():
            return "Error: nama dan goal tidak boleh kosong."
        conn = psycopg2.connect(DATABASE_URL)
        try:
            cur = conn.cursor()
            _proj_ensure_table(cur)
            cur.execute(
                "UPDATE proyek SET goal = %s, status = %s, updated_at = NOW() WHERE user_id = %s AND nama = %s;",
                (goal.strip()[:1000], status, _proj_user(), nama),
            )
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT INTO proyek(nama, goal, status, user_id) VALUES (%s, %s, %s, %s);",
                    (nama, goal.strip()[:1000], status, _proj_user()),
                )
            conn.commit()
            return f"Proyek tersimpan: {nama} [{status}]"
        finally:
            conn.close()
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def catat_proyek(nama: str, catatan: str) -> str:
    """Tambah catatan perkembangan ke proyek yang ada (append, bukan timpa).

    Args:
        nama: Nama proyek (lihat via lihat_proyek).
        catatan: Perkembangan/keputusan baru. Contoh: "sudah pilih keramik, lanjut tukang".
    """
    try:
        import psycopg2

        from src.config.routing_keywords_pg import DATABASE_URL

        nama = nama.strip().lower().replace(" ", "-")[:60]
        conn = psycopg2.connect(DATABASE_URL)
        try:
            cur = conn.cursor()
            _proj_ensure_table(cur)
            cur.execute(
                "SELECT catatan FROM proyek WHERE user_id = %s AND nama = %s;",
                (_proj_user(), nama),
            )
            row = cur.fetchone()
            if not row:
                return f"Error: proyek '{nama}' tidak ada. Simpan dulu via simpan_proyek."
            merged = ((row[0] + " | " if row[0] else "") + catatan.strip())[:2000]
            cur.execute(
                "UPDATE proyek SET catatan = %s, updated_at = NOW() WHERE user_id = %s AND nama = %s;",
                (merged, _proj_user(), nama),
            )
            conn.commit()
            return f"Catatan ditambah ke proyek {nama}."
        finally:
            conn.close()
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def lihat_proyek() -> str:
    """Lihat semua proyek aktif user beserta goal dan catatannya."""
    block = get_projects_block()
    return block or "Belum ada proyek aktif."
