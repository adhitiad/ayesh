"""Manage routing keywords in PostgreSQL long term memory."""
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL tidak ditemukan di .env, pakai fallback file.")
    sys.exit(0)

import psycopg2


def get_conn():
    return psycopg2.connect(DATABASE_URL)

def ensure_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS routing_keywords (
            agent VARCHAR(50) NOT NULL,
            keyword VARCHAR(100) NOT NULL,
            allowed_tools JSONB DEFAULT '[]'::jsonb,
            PRIMARY KEY (agent, keyword)
        );
    """)
    # Tambah kolom jika belum ada (migrasi)
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'routing_keywords' AND column_name = 'allowed_tools';
    """)
    if cur.fetchone() is None:
        cur.execute("ALTER TABLE routing_keywords ADD COLUMN allowed_tools JSONB DEFAULT '[]'::jsonb;")
    conn.commit()
    conn.close()

def add_keyword(agent, keyword, allowed_tools=None):
    ensure_table()
    tools_json = json.dumps(allowed_tools or [])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO routing_keywords(agent, keyword, allowed_tools)
           VALUES (%s,%s,%s::jsonb) ON CONFLICT (agent, keyword)
           DO UPDATE SET allowed_tools = EXCLUDED.allowed_tools;""",
        (agent, keyword.lower(), tools_json)
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Added {keyword} -> {agent} (tools: {allowed_tools or []})")

def remove_keyword(agent, keyword):
    ensure_table()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM routing_keywords WHERE agent=%s AND keyword=%s;", (agent, keyword.lower()))
    conn.commit()
    cur.close()
    conn.close()
    print(f"Removed {keyword} from {agent}")

def list_keywords():
    ensure_table()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT agent, keyword, allowed_tools FROM routing_keywords ORDER BY agent, keyword;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    current = {}
    for agent, kw, tools in rows:
        current.setdefault(agent, []).append((kw, tools or []))
    for agent, kws in current.items():
        print(f"\n{agent}:")
        for kw, tools in kws:
            tools_str = ", ".join(tools) if tools else "(no tools)"
            print(f"  - {kw} -> [{tools_str}]")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["add", "remove", "list"])
    p.add_argument("--agent", required=False)
    p.add_argument("--keyword", required=False)
    p.add_argument("--tools", required=False, help="Comma-separated tool names, e.g. tulis_kode,baca_file")
    args = p.parse_args()
    if args.action == "list":
        list_keywords()
    elif args.action == "add":
        if not args.agent or not args.keyword:
            print("add perlu --agent dan --keyword")
            sys.exit(1)
        tools = [t.strip() for t in args.tools.split(",")] if args.tools else []
        add_keyword(args.agent, args.keyword, tools)
    elif args.action == "remove":
        if not args.agent or not args.keyword:
            print("remove perlu --agent dan --keyword")
            sys.exit(1)
        remove_keyword(args.agent, args.keyword)
