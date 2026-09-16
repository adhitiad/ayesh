"""Manage routing keywords in PostgreSQL long term memory."""
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
            PRIMARY KEY (agent, keyword)
        );
    """)
    conn.commit()
    conn.close()

def add_keyword(agent, keyword):
    ensure_table()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO routing_keywords(agent, keyword) VALUES (%s,%s) ON CONFLICT DO NOTHING;",
        (agent, keyword.lower())
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Added {keyword} -> {agent}")

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
    cur.execute("SELECT agent, keyword FROM routing_keywords ORDER BY agent, keyword;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    current = {}
    for agent, kw in rows:
        current.setdefault(agent, []).append(kw)
    for agent, kws in current.items():
        print(f"{agent}: {', '.join(kws)}")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["add","remove","list"])
    p.add_argument("--agent", required=False)
    p.add_argument("--keyword", required=False)
    args = p.parse_args()
    if args.action == "list":
        list_keywords()
    elif args.action == "add":
        if not args.agent or not args.keyword:
            print("add perlu --agent dan --keyword")
            sys.exit(1)
        add_keyword(args.agent, args.keyword)
    elif args.action == "remove":
        if not args.agent or not args.keyword:
            print("remove perlu --agent dan --keyword")
            sys.exit(1)
        remove_keyword(args.agent, args.keyword)
