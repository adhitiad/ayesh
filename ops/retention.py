"""Retensi: hapus baris lama agar tabel operasional tak membengkak.

Target: logs, request_stats, background_tasks (status final), plus data auth
kedaluwarsa (auth_sessions expired/revoked, auth_tokens expired — termasuk
2fa_challenge/email_verify/reset yang sudah mati, auth_oauth_states lewat TTL).
TIDAK PERNAH: audit_log (rantai hash), sessions, preferensi, proyek.

Pakai:  python -m ops.retention [--days-logs 30] [--days-stats 90] [--days-tasks 30] [--days-auth 30]
"""

import argparse

# Hapus auth bila expired/revoked sudah lewat N hari (beri jendela aman utk audit).
_AUTH_JOBS = [
    (
        "auth_sessions",
        (
            "DELETE FROM auth_sessions "
            "WHERE expires_at < NOW() - (%s || ' days')::INTERVAL "
            "OR (revoked_at IS NOT NULL AND revoked_at < NOW() - (%s || ' days')::INTERVAL)"
        ),
        2,
    ),
    ("auth_tokens", "DELETE FROM auth_tokens WHERE expires_at < NOW() - (%s || ' days')::INTERVAL", 1),
    ("auth_oauth_states", "DELETE FROM auth_oauth_states WHERE expires_at < NOW()", 0),
]


def purge(days_logs: int = 30, days_stats: int = 90, days_tasks: int = 30, days_auth: int = 30) -> dict:
    from src.core.db.db import connect

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
        cur.execute(
            "DELETE FROM background_tasks WHERE status IN ('done', 'error') "
            "AND updated_at < NOW() - (%s || ' days')::INTERVAL;",
            (str(days_tasks),),
        )
        out["background_tasks"] = cur.rowcount
    except Exception as e:
        out["background_tasks"] = f"skip: {str(e)[:100]}"
    for table, sql, n_params in _AUTH_JOBS:
        try:
            params = tuple(str(days_auth) for _ in range(n_params))
            cur.execute(sql + ";", params)
            out[table] = cur.rowcount
        except Exception as e:
            out[table] = f"skip: {str(e)[:100]}"
    conn.close()
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Hapus baris lama tabel operasional")
    p.add_argument("--days-logs", type=int, default=30)
    p.add_argument("--days-stats", type=int, default=90)
    p.add_argument("--days-tasks", type=int, default=30)
    p.add_argument("--days-auth", type=int, default=30)
    args = p.parse_args()
    for table, n in purge(args.days_logs, args.days_stats, args.days_tasks, args.days_auth).items():
        print(f"  {table}: {n}")
