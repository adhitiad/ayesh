"""Scheduled tasks: pekerjaan agen terjadwal (interval / harian WIB).

Jadwal didukung:
- interval_detik: tiap N detik sejak last_run (atau sejak dibuat).
- daily_at: "HH:MM" WIB tiap hari.

Eksekusi via route_request() dengan session job. Loop jalan di thread
terpisah; aktif hanya bila env ENABLE_SCHEDULER=1 (default mati agar
import/test tidak men-spawn thread).
"""

import threading
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            interval_detik INTEGER NULL,
            daily_at TEXT NULL,
            session_id TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            last_run TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def _now_wib() -> datetime:
    return datetime.now(WIB)


def is_due(job: dict, now: datetime | None = None) -> bool:
    """Pure: apakah job jatuh tempo? job = {interval_detik, daily_at, last_run}."""
    now = now or _now_wib()
    if isinstance(now, str):
        now = datetime.fromisoformat(now)
    if now.tzinfo is None:
        now = now.replace(tzinfo=WIB)
    last = job.get("last_run")
    if isinstance(last, str):
        last = datetime.fromisoformat(last)
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=WIB)

    interval = job.get("interval_detik")
    if interval:
        if last is None:
            return True
        return (now - last).total_seconds() >= int(interval)

    daily_at = (job.get("daily_at") or "").strip()
    if daily_at:
        try:
            hh, mm = (int(x) for x in daily_at.split(":"))
        except ValueError:
            return False
        today_slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now < today_slot:
            return False
        if last is None:
            return True
        return last < today_slot
    return False


def _conn():
    from core.db import connect
    return connect()


def create_job(name: str, prompt: str, interval_detik: int | None = None,
               daily_at: str | None = None, session_id: str | None = None) -> dict:
    import uuid
    if not interval_detik and not daily_at:
        raise ValueError("Isi interval_detik atau daily_at.")
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    sid = session_id or f"job_{uuid.uuid4().hex[:8]}"
    cur.execute(
        "INSERT INTO scheduled_jobs(name, prompt, interval_detik, daily_at, session_id)"
        " VALUES (%s, %s, %s, %s, %s) RETURNING id;",
        (name.strip()[:100], prompt.strip()[:2000], interval_detik, daily_at, sid),
    )
    jid = cur.fetchone()[0]
    conn.close()
    return {"id": jid, "name": name, "session_id": sid}


def list_jobs() -> list:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT id, name, prompt, interval_detik, daily_at, session_id, enabled, last_run FROM scheduled_jobs ORDER BY id;")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "prompt": (r[2] or "")[:200], "interval_detik": r[3],
             "daily_at": r[4], "session_id": r[5], "enabled": r[6],
             "last_run": str(r[7]) if r[7] else None} for r in rows]


def delete_job(job_id: int) -> bool:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute("DELETE FROM scheduled_jobs WHERE id = %s;", (job_id,))
    n = cur.rowcount
    conn.close()
    return n > 0


def set_enabled(job_id: int, enabled: bool) -> bool:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute("UPDATE scheduled_jobs SET enabled = %s WHERE id = %s;", (enabled, job_id))
    n = cur.rowcount
    conn.close()
    return n > 0


def run_due_jobs() -> list:
    """Jalankan semua job enabled yang jatuh tempo. Return hasil per job."""
    from main import route_request
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT id, name, prompt, interval_detik, daily_at, session_id, last_run FROM scheduled_jobs WHERE enabled = TRUE;")
    rows = cur.fetchall()
    conn.close()
    now = _now_wib()
    out = []
    for (jid, name, prompt, interval_detik, daily_at, session_id, last_run) in rows:
        job = {"interval_detik": interval_detik, "daily_at": daily_at, "last_run": last_run}
        if not is_due(job, now):
            continue
        try:
            res = route_request(prompt, session_id)
            status, note = "ok", str(res.get("answer", ""))[:200]
        except Exception as e:
            status, note = "error", str(e)[:200]
        conn2 = _conn()
        cur2 = conn2.cursor()
        cur2.execute("UPDATE scheduled_jobs SET last_run = NOW() WHERE id = %s;", (jid,))
        conn2.close()
        out.append({"id": jid, "name": name, "status": status, "note": note})
    return out


_scheduler_thread = None
_scheduler_stop = threading.Event()


def _loop(poll_detik: int = 60):
    while not _scheduler_stop.is_set():
        try:
            done = run_due_jobs()
            if done:
                import logging
                logging.getLogger("scheduler").info(f"Jobs selesai: {[(d['id'], d['status']) for d in done]}")
        except Exception:
            pass
        _scheduler_stop.wait(poll_detik)


def start_scheduler(poll_detik: int = 60) -> bool:
    """Start background thread. Return False bila sudah jalan."""
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return False
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_loop, args=(poll_detik,), daemon=True)
    _scheduler_thread.start()
    return True


def stop_scheduler():
    _scheduler_stop.set()
