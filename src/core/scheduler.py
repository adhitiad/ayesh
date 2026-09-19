"""Scheduled tasks: pekerjaan agen terjadwal (interval / harian WIB).

Jadwal didukung:
- interval_detik: tiap N detik sejak last_run (atau sejak dibuat).
- daily_at: "HH:MM" WIB tiap hari.

Eksekusi via route_request() dengan session job. Loop jalan di thread
terpisah; aktif hanya bila env ENABLE_SCHEDULER=1 (default mati agar
import/test tidak men-spawn thread).
"""

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            interval_detik INTEGER NULL,
            daily_at TEXT NULL,
            session_id TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            user_id TEXT NOT NULL DEFAULT 'default',
            allowed_tools TEXT NOT NULL DEFAULT '[]',
            approval_policy TEXT NOT NULL DEFAULT 'deny_all',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            last_run TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    # Migration: alter id column from SERIAL to TEXT if needed
    cur.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'scheduled_jobs' AND column_name = 'id'
                AND data_type != 'text'
            ) THEN
                ALTER TABLE scheduled_jobs ALTER COLUMN id TYPE TEXT USING id::TEXT;
            END IF;
        END $$;
    """)
    # Migration: add owner_user_id column if missing
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'scheduled_jobs' AND column_name = 'owner_user_id'
            ) THEN
                ALTER TABLE scheduled_jobs ADD COLUMN owner_user_id TEXT NOT NULL DEFAULT 'default';
            END IF;
        END $$;
    """)
    # Migration: add allowed_tools column if missing
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'scheduled_jobs' AND column_name = 'allowed_tools'
            ) THEN
                ALTER TABLE scheduled_jobs ADD COLUMN allowed_tools TEXT NOT NULL DEFAULT '[]';
            END IF;
        END $$;
    """)
    # Migration: add approval_policy column if missing
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'scheduled_jobs' AND column_name = 'approval_policy'
            ) THEN
                ALTER TABLE scheduled_jobs ADD COLUMN approval_policy TEXT NOT NULL DEFAULT 'deny_all';
            END IF;
        END $$;
    """)
    # Migration: add user_id column if missing
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'scheduled_jobs' AND column_name = 'user_id'
            ) THEN
                ALTER TABLE scheduled_jobs ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';
            END IF;
        END $$;
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
    from src.core.db import connect

    return connect()


def create_job(
    name: str,
    prompt: str,
    interval_detik: int | None = None,
    daily_at: str | None = None,
    session_id: str | None = None,
    user_id: str = "default",
    owner_user_id: str | None = None,
    allowed_tools: list | None = None,
    approval_policy: str = "deny_all",
) -> dict:
    if not interval_detik and not daily_at:
        raise ValueError("Isi interval_detik atau daily_at.")
    if not owner_user_id:
        owner_user_id = user_id
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    jid = str(uuid.uuid4())
    sid = session_id or str(uuid.uuid4())
    tools_json = json.dumps(allowed_tools or [])
    cur.execute(
        "INSERT INTO scheduled_jobs(id, name, prompt, interval_detik, daily_at, session_id, owner_user_id, user_id, allowed_tools, approval_policy)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            jid,
            name.strip()[:100],
            prompt.strip()[:2000],
            interval_detik,
            daily_at,
            sid,
            owner_user_id,
            user_id,
            tools_json,
            approval_policy,
        ),
    )
    conn.close()
    return {
        "id": jid,
        "name": name,
        "session_id": sid,
        "owner_user_id": owner_user_id,
        "user_id": user_id,
        "allowed_tools": allowed_tools or [],
        "approval_policy": approval_policy,
    }


def list_jobs(user_id: str = "default") -> list:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute(
        "SELECT id, name, prompt, interval_detik, daily_at, session_id, owner_user_id, user_id, allowed_tools, approval_policy, enabled, last_run FROM scheduled_jobs WHERE user_id = %s ORDER BY id;",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "name": r[1],
            "prompt": (r[2] or "")[:200],
            "interval_detik": r[3],
            "daily_at": r[4],
            "session_id": r[5],
            "owner_user_id": r[6],
            "user_id": r[7],
            "allowed_tools": json.loads(r[8] or "[]"),
            "approval_policy": r[9] or "deny_all",
            "enabled": r[10],
            "last_run": str(r[11]) if r[11] else None,
        }
        for r in rows
    ]


def delete_job(job_id: str, owner_user_id: str = "default") -> bool:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute(
        "DELETE FROM scheduled_jobs WHERE id = %s AND owner_user_id = %s;",
        (job_id, owner_user_id),
    )
    n = cur.rowcount
    conn.close()
    return n > 0


def set_enabled(job_id: str, enabled: bool, owner_user_id: str = "default") -> bool:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute(
        "UPDATE scheduled_jobs SET enabled = %s WHERE id = %s AND owner_user_id = %s;",
        (enabled, job_id, owner_user_id),
    )
    n = cur.rowcount
    conn.close()
    return n > 0


def _check_capability(job: dict, tool_name: str, args: dict = None) -> bool:
    """Check if a scheduled job is allowed to use a specific tool."""
    allowed_tools = job.get("allowed_tools", [])
    approval_policy = job.get("approval_policy", "deny_all")
    if approval_policy == "allow_all":
        return True
    if tool_name in allowed_tools:
        return True
    return False


def run_due_jobs() -> list:
    """Jalankan semua job enabled yang jatuh tempo. Return hasil per job."""
    from main import route_request

    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute(
        "SELECT id, name, prompt, interval_detik, daily_at, session_id, owner_user_id, user_id, allowed_tools, approval_policy, last_run FROM scheduled_jobs WHERE enabled = TRUE;"
    )
    rows = cur.fetchall()
    conn.close()
    now = _now_wib()
    out = []
    for (
        jid,
        name,
        prompt,
        interval_detik,
        daily_at,
        session_id,
        owner_user_id,
        user_id,
        allowed_tools,
        approval_policy,
        last_run,
    ) in rows:
        job = {
            "interval_detik": interval_detik,
            "daily_at": daily_at,
            "last_run": last_run,
            "allowed_tools": json.loads(allowed_tools or "[]"),
            "approval_policy": approval_policy or "deny_all",
        }
        if not is_due(job, now):
            continue
        try:
            res = route_request(prompt, session_id)
            status, note = "ok", str(res.get("answer", ""))[:200]
        except Exception as e:
            status, note = "error", str(e)[:200]
        conn2 = _conn()
        cur2 = conn2.cursor()
        cur2.execute(
            "UPDATE scheduled_jobs SET last_run = NOW() WHERE id = %s;", (jid,)
        )
        conn2.close()
        out.append(
            {
                "id": jid,
                "name": name,
                "status": status,
                "note": note,
                "owner_user_id": owner_user_id,
            }
        )
    return out


_scheduler_thread = None
_scheduler_stop = threading.Event()


def _loop(poll_detik: int = 60):
    while not _scheduler_stop.is_set():
        try:
            done = run_due_jobs()
            if done:
                import logging

                logging.getLogger("scheduler").info(
                    f"Jobs selesai: {[(d['id'], d['status']) for d in done]}"
                )
        except Exception as _e:
            import logging

            logging.getLogger(__name__).debug("scheduler run_due_jobs error: %s", _e)
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
