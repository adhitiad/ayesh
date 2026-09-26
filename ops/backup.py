"""Backup/restore JSON semua tabel app (tanpa butuh pg_dump binary).

Pakai:
  python -m ops.backup backup                    # → backup_YYYYMMDD_HHMMSS.json
  python -m ops.backup backup --out f.json
  python -m ops.backup restore --in f.json       # TRUNCATE + INSERT + setval
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

TABLES = [
    "sessions",
    "routing_keywords",
    "session_memory",
    "logs",
    "feedback",
    "tool_failures",
    "routing_learnings",
    "preferensi",
    "proyek",
    "scheduled_jobs",
    "background_tasks",
    "pending_approvals",
    "audit_log",
    "request_stats",
    # Data identitas & uang (ditambahkan 2026-09 — sebelumnya tidak ikut backup)
    "users",
    "vip_upgrades",
    "auth_sessions",
    "auth_tokens",
    "auth_oauth_states",
    "user_llm_configs",
    "user_skill_overrides",
    "user_mcp_overrides",
    "plans",
    "plan_steps",
    "monologues",
]


def _conn():
    from src.core.db.db import connect

    return connect()


def dump_all() -> dict:
    conn = _conn()
    cur = conn.cursor()
    out: dict[str, Any] = {"version": 1, "dumped_at": datetime.now().isoformat(), "tables": {}}
    for table in TABLES:
        try:
            cur.execute(f"SELECT * FROM {table};")
            cols = [d[0] for d in cur.description]
            rows = []
            for r in cur.fetchall():
                rows.append(
                    {c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in zip(cols, r, strict=False)}
                )
            out["tables"][table] = {"columns": cols, "rows": rows}
        except Exception as e:
            out["tables"][table] = {"error": str(e)[:200], "rows": []}
    conn.close()
    return out


def backup_to(path: str | None = None) -> str:
    data = dump_all()
    if path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"backup_{stamp}.json"
    Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    total = sum(len(t.get("rows", [])) for t in data["tables"].values())
    print(f"Backup OK: {path} ({total} baris, {len(data['tables'])} tabel)")
    return path


def restore_from(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    conn = _conn()
    cur = conn.cursor()
    stats = {}
    for table, tdata in data.get("tables", {}).items():
        if table not in TABLES or "rows" not in tdata or not tdata["rows"]:
            stats[table] = "skip"
            continue
        cols = tdata.get("columns") or list(tdata["rows"][0].keys())
        try:
            cur.execute(f"TRUNCATE {table} RESTART IDENTITY CASCADE;")
            for row in tdata["rows"]:
                vals = [row.get(c) for c in cols]
                placeholders = ", ".join(["%s"] * len(cols))
                cur.execute(
                    f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders});",
                    vals,
                )
            # Kembalikan sequence bila ada kolom id SERIAL
            if "id" in cols:
                try:
                    cur.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table};"
                    )
                except Exception:
                    pass  # Non-critical: sequence reset best-effort
            stats[table] = f"{len(tdata['rows'])} rows"
        except Exception as e:
            stats[table] = f"error: {str(e)[:150]}"
    conn.close()
    return stats


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Backup/restore database app")
    p.add_argument("action", choices=["backup", "restore"])
    p.add_argument("--out", default=None)
    p.add_argument("--in", dest="inp", default=None)
    args = p.parse_args()
    if args.action == "backup":
        backup_to(args.out)
    else:
        if not args.inp:
            sys.exit("--in wajib untuk restore")
        for table, status in restore_from(args.inp).items():
            print(f"  {table}: {status}")
