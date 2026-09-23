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


def _ensure_table(cur=None):
    """Ensure scheduled_jobs table exists. Accepts cursor (no-op) for backward compat."""
    from src.core.db.db_engine import get_engine
    from src.core.db.models import Base, ScheduledJob

    Base.metadata.create_all(get_engine(), tables=[ScheduledJob.__table__])


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
    from src.core.db.db import connect

    return connect()


def _SessionLocal():
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine

    return sessionmaker(bind=get_engine())


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
    if interval_detik is not None and interval_detik <= 0:
        raise ValueError("interval_detik harus bilangan positif.")
    if daily_at is not None:
        import re

        if not re.fullmatch(r"\d{2}:\d{2}", daily_at):
            raise ValueError("daily_at format harus 'HH:MM' (contoh: '08:30').")
        hh, mm = daily_at.split(":")
        if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError("daily_at: jam harus 00-23, menit harus 00-59.")
    if not owner_user_id:
        owner_user_id = user_id

    _ensure_table()
    SessionLocal = _SessionLocal()

    # Per-user job count limit (configurable via env; skip in pytest)
    import os

    _testing = os.getenv("PYTEST_CURRENT_TEST") is not None
    _MAX_JOBS_PER_USER = int(os.getenv("MAX_JOBS_PER_USER", "100"))
    with SessionLocal() as db:
        from sqlalchemy import func

        from src.core.db.models import ScheduledJob

        active_count = (
            db.query(func.count()).filter(ScheduledJob.owner_user_id == owner_user_id, ScheduledJob.enabled).scalar()
        )
        if not _testing and active_count >= _MAX_JOBS_PER_USER:
            raise ValueError(f"Batas job terlampaui (max {_MAX_JOBS_PER_USER} aktif per user).")

    jid = str(uuid.uuid4())
    sid = session_id or str(uuid.uuid4())
    tools_json = json.dumps(allowed_tools or [])

    with SessionLocal() as db:
        from src.core.db.models import ScheduledJob

        job = ScheduledJob(
            id=jid,
            name=name.strip()[:100],
            prompt=prompt.strip()[:2000],
            interval_detik=interval_detik,
            daily_at=daily_at,
            session_id=sid,
            owner_user_id=owner_user_id,
            user_id=user_id,
            allowed_tools=tools_json,
            approval_policy=approval_policy,
            enabled=True,
        )
        db.add(job)
        db.commit()
    return {
        "id": jid,
        "name": name,
        "session_id": sid,
        "owner_user_id": owner_user_id,
        "user_id": user_id,
        "allowed_tools": allowed_tools or [],
        "approval_policy": approval_policy,
    }


def list_jobs(user_id: str = "default", offset: int = 0, limit: int = 50) -> list:
    _ensure_table()
    SessionLocal = _SessionLocal()
    with SessionLocal() as db:
        from src.core.db.models import ScheduledJob

        rows = (
            db.query(ScheduledJob)
            .filter(ScheduledJob.user_id == user_id)
            .order_by(ScheduledJob.id)
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "name": r.name,
                "prompt": (r.prompt or "")[:200],
                "interval_detik": r.interval_detik,
                "daily_at": r.daily_at,
                "session_id": r.session_id,
                "owner_user_id": r.owner_user_id,
                "user_id": r.user_id,
                "allowed_tools": json.loads(r.allowed_tools or "[]"),
                "approval_policy": r.approval_policy or "deny_all",
                "enabled": r.enabled,
                "last_run": str(r.last_run) if r.last_run else None,
            }
            for r in rows
        ]


def delete_job(job_id: str, owner_user_id: str = "default") -> bool:
    _ensure_table()
    SessionLocal = _SessionLocal()
    with SessionLocal() as db:
        from src.core.db.models import ScheduledJob

        n = (
            db.query(ScheduledJob)
            .filter(ScheduledJob.id == job_id, ScheduledJob.owner_user_id == owner_user_id)
            .delete()
        )
        db.commit()
        return n > 0


def set_enabled(job_id: str, enabled: bool, owner_user_id: str = "default") -> bool:
    _ensure_table()
    SessionLocal = _SessionLocal()
    with SessionLocal() as db:
        from src.core.db.models import ScheduledJob

        job = (
            db.query(ScheduledJob)
            .filter(ScheduledJob.id == job_id, ScheduledJob.owner_user_id == owner_user_id)
            .first()
        )
        if not job:
            return False
        job.enabled = enabled
        db.commit()
        return True


def _check_capability(job: dict, tool_name: str, args: dict | None = None) -> bool:
    """Check if a scheduled job is allowed to use a specific tool."""
    allowed_tools = job.get("allowed_tools", [])
    approval_policy = job.get("approval_policy", "deny_all")
    if approval_policy == "allow_all":
        return True
    return tool_name in allowed_tools


def run_due_jobs() -> list:
    """Jalankan semua job enabled yang jatuh tempo. Return hasil per job."""
    from main import route_request

    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_table(cur)
        conn.commit()
        cur.execute(
            "SELECT id, name, prompt, interval_detik, daily_at, session_id, owner_user_id, user_id, allowed_tools, approval_policy, last_run FROM scheduled_jobs WHERE enabled = TRUE;"
        )
        rows = cur.fetchall()
    finally:
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
        _user_id,
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
        try:
            cur2 = conn2.cursor()
            cur2.execute("UPDATE scheduled_jobs SET last_run = NOW() WHERE id = %s;", (jid,))
            conn2.commit()
        finally:
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

                logging.getLogger("scheduler").info(f"Jobs selesai: {[(d['id'], d['status']) for d in done]}")
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


def stop_scheduler(timeout: float = 5.0) -> bool:
    """Stop background scheduler thread gracefully. Return True bila berhasil stop."""
    global _scheduler_thread
    if not _scheduler_thread or not _scheduler_thread.is_alive():
        return True
    _scheduler_stop.set()
    _scheduler_thread.join(timeout=timeout)
    if _scheduler_thread.is_alive():
        return False
    _scheduler_thread = None
    return True
