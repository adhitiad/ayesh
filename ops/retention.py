"""Retensi: hapus baris lama agar tabel operasional tak membengkak.

Target: logs, request_stats, background_tasks (status final).
TIDAK PERNAH: audit_log (rantai hash), sessions, preferensi, proyek.

Pakai:  python -m ops.retention [--days-logs 30] [--days-stats 90] [--days-tasks 30]
"""

import argparse


def purge(days_logs: int = 30, days_stats: int = 90, days_tasks: int = 30) -> dict:
    from src.core.db import connect
    conn = connect()
    cur = conn.cursor()
    out = {}
    jobs = [
        ("logs", "timestamp", days_logs),
        ("request_stats", "ts", days_stats),
    ]
    for table, col, days in jobs:
        try:
            cur.execute(f"DELETE FROM {table} WHERE {col} < NOW() - (%s || ' days')::INTERVAL;", (str(days),))
            out[table] = cur.rowcount
        except Exception as e:
            out[table] = f"skip: {str(e)[:100]}"
    try:
        cur.execute("DELETE FROM background_tasks WHERE status IN ('done', 'error') "
                    "AND updated_at < NOW() - (%s || ' days')::INTERVAL;", (str(days_tasks),))
        out["background_tasks"] = cur.rowcount
    except Exception as e:
        out["background_tasks"] = f"skip: {str(e)[:100]}"
    conn.close()
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Hapus baris lama tabel operasional")
    p.add_argument("--days-logs", type=int, default=30)
    p.add_argument("--days-stats", type=int, default=90)
    p.add_argument("--days-tasks", type=int, default=30)
    args = p.parse_args()
    for table, n in purge(args.days_logs, args.days_stats, args.days_tasks).items():
        print(f"  {table}: {n}")
