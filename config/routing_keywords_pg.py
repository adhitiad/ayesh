# Long term memory routing keywords via PostgreSQL
# Fallback ke file jika Postgres tidak tersedia

import os
from dotenv import load_dotenv
from typing import Dict, List

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def _load_from_file() -> Dict[str, List[str]]:
    try:
        from config.routing_keywords import ROUTING_KEYWORDS, DEFAULT_AGENT
        return ROUTING_KEYWORDS, DEFAULT_AGENT
    except Exception:
        return {}, "casual_agent"

def get_routing_keywords() -> tuple[Dict[str, List[str]], str]:
    # Coba Postgres dulu
    if DATABASE_URL:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor

            # Buat tabel jika belum ada
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS routing_keywords (
                    agent VARCHAR(50) NOT NULL,
                    keyword VARCHAR(100) NOT NULL,
                    PRIMARY KEY (agent, keyword)
                );
            """)
            # Jika tabel kosong, seed dari file
            cur.execute("SELECT COUNT(*) FROM routing_keywords;")
            count = cur.fetchone()[0]
            if count == 0:
                from config.routing_keywords import ROUTING_KEYWORDS
                for agent, kws in ROUTING_KEYWORDS.items():
                    for kw in kws:
                        cur.execute(
                            "INSERT INTO routing_keywords(agent, keyword) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                            (agent, kw)
                        )
                conn.commit()

            # Load keywords
            cur.execute("SELECT agent, keyword FROM routing_keywords ORDER BY agent;")
            rows = cur.fetchall()
            conn.close()

            keywords: Dict[str, List[str]] = {}
            for agent, kw in rows:
                keywords.setdefault(agent, []).append(kw)
            # Default agent dari file
            _, default_agent = _load_from_file()
            return keywords, default_agent
        except Exception as e:
            # Fallback ke file
            print(f"Postgres routing keywords gagal: {e}")
    
    return _load_from_file()
