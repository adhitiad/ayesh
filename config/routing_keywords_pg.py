# Long term memory routing keywords via PostgreSQL
# Fallback ke default jika Postgres tidak tersedia

import os
import json
from functools import lru_cache
from dotenv import load_dotenv
from typing import Dict, List, Tuple, Any

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

DEFAULT_KEYWORDS: Dict[str, List[str]] = {
    "coder_agent": ["kode", "program", "python", "script", "deploy"],
    "admin_agent": ["draf", "gaji", "upah", "surat", "izin"],
}
DEFAULT_AGENT = "casual_agent"


def _load_from_file() -> Tuple[Dict[str, List[str]], str]:
    return DEFAULT_KEYWORDS, DEFAULT_AGENT


def _upgrade_table_if_needed(cur):
    """Tambah kolom allowed_tools jika belum ada (migrasi)."""
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'routing_keywords' AND column_name = 'allowed_tools';
    """)
    if cur.fetchone() is None:
        cur.execute(
            "ALTER TABLE routing_keywords ADD COLUMN allowed_tools JSONB DEFAULT '[]'::jsonb;"
        )


def _migrate_file_data(cur, file_keywords: Dict[str, List[str]]):
    """Insert data default dari file ke Postgres jika tabel kosong."""
    cur.execute("SELECT COUNT(*) FROM routing_keywords;")
    count = cur.fetchone()[0]
    if count > 0:
        return

    default_tools_map = {
        "coder_agent": ["tulis_kode", "baca_file"],
        "admin_agent": ["cari_web"],
        "casual_agent": [],
    }
    for agent, kws in file_keywords.items():
        tools = json.dumps(default_tools_map.get(agent, []))
        for kw in kws:
            cur.execute(
                """INSERT INTO routing_keywords(agent, keyword, allowed_tools)
                   VALUES (%s, %s, %s::jsonb) ON CONFLICT DO NOTHING;""",
                (agent, kw, tools),
            )


def invalidate_routing_cache():
    """Reset cache agar keyword baru terbaca."""
    get_routing_keywords.cache_clear()
    get_routing_keywords_with_tools.cache_clear()


@lru_cache(maxsize=1)
def get_routing_keywords() -> Tuple[Dict[str, List[str]], str]:
    """Return (keywords_dict, default_agent).

    keywords_dict format: {agent: [keyword1, keyword2, ...]}
    compatible dengan semua code lama yang sudah import fungsi ini.
    """
    if DATABASE_URL:
        try:
            import psycopg2

            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS routing_keywords (
                    agent VARCHAR(50) NOT NULL,
                    keyword VARCHAR(100) NOT NULL,
                    allowed_tools JSONB DEFAULT '[]'::jsonb,
                    PRIMARY KEY (agent, keyword)
                );
            """)
            _upgrade_table_if_needed(cur)

            file_keywords, default_agent = _load_from_file()
            _migrate_file_data(cur, file_keywords)
            conn.commit()

            cur.execute("SELECT agent, keyword FROM routing_keywords ORDER BY agent;")
            rows = cur.fetchall()
            conn.close()

            keywords: Dict[str, List[str]] = {}
            for agent, kw in rows:
                keywords.setdefault(agent, []).append(kw)
            _, default_agent = _load_from_file()
            return keywords, default_agent
        except Exception as e:
            print(f"Postgres routing keywords gagal: {e}")

    return _load_from_file()


@lru_cache(maxsize=1)
def get_routing_keywords_with_tools() -> Tuple[Dict[str, Dict[str, Any]], str]:
    """Return format baru: {agent: {keyword: {allowed_tools: [...]}}}.

    Untuk tool filtering berbasis per-keyword.
    """
    if DATABASE_URL:
        try:
            import psycopg2

            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS routing_keywords (
                    agent VARCHAR(50) NOT NULL,
                    keyword VARCHAR(100) NOT NULL,
                    allowed_tools JSONB DEFAULT '[]'::jsonb,
                    PRIMARY KEY (agent, keyword)
                );
            """)
            _upgrade_table_if_needed(cur)

            file_keywords, default_agent = _load_from_file()
            _migrate_file_data(cur, file_keywords)
            conn.commit()

            cur.execute(
                "SELECT agent, keyword, allowed_tools FROM routing_keywords ORDER BY agent;"
            )
            rows = cur.fetchall()
            conn.close()

            result: Dict[str, Dict[str, Any]] = {}
            for agent, kw, tools in rows:
                if agent not in result:
                    result[agent] = {}
                tools_list = tools if isinstance(tools, list) else []
                result[agent][kw] = {"allowed_tools": tools_list}
            return result, default_agent
        except Exception as e:
            print(f"Postgres routing keywords (with tools) gagal: {e}")

    file_keywords, default_agent = _load_from_file()
    result = {}
    for agent, kws in file_keywords.items():
        result[agent] = {}
        for kw in kws:
            result[agent][kw] = {"allowed_tools": []}
    return result, default_agent


def update_keyword_tools(agent: str, keyword: str, allowed_tools: List[str]) -> bool:
    """Update allowed_tools untuk keyword tertentu."""
    if not DATABASE_URL:
        return False
    try:
        import psycopg2

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE routing_keywords SET allowed_tools = %s::jsonb
            WHERE agent = %s AND keyword = %s;
        """,
            (json.dumps(allowed_tools), agent, keyword.lower()),
        )
        updated = cur.rowcount
        conn.commit()
        conn.close()
        return updated > 0
    except Exception as e:
        print(f"Gagal update keyword tools: {e}")
        return False


def add_keyword_with_tools(agent: str, keyword: str, allowed_tools: List[str]) -> bool:
    """Insert atau update keyword beserta allowed_tools."""
    if not DATABASE_URL:
        return False
    try:
        import psycopg2

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Check if table has primary key on (agent, keyword)
        cur.execute(
            """
            INSERT INTO routing_keywords(agent, keyword, allowed_tools)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (agent, keyword) DO UPDATE SET allowed_tools = EXCLUDED.allowed_tools;
        """,
            (agent, keyword.lower(), json.dumps(allowed_tools)),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Gagal add keyword with tools: {e}")
        return False
