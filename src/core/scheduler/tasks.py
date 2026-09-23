"""Async task queue: request lambat jadi background job.

POST /tasks → 202 {task_id}; worker thread-pool jalankan route_request;
GET /tasks/{id} untuk poll status + hasil. Tabel: background_tasks.
"""

import json as _json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func

_executor = ThreadPoolExecutor(max_workers=4)
_lock = threading.Lock()
logger = logging.getLogger(__name__)

_MAX_TASKS_PER_USER = 10  # Max pending+running tasks per user


def _ensure_table(cur=None):
    """Ensure background_tasks table exists. Accepts cursor (no-op) for backward compat."""
    from src.core.db.db_engine import get_engine
    from src.core.db.models import BackgroundTask, Base

    Base.metadata.create_all(get_engine(), tables=[BackgroundTask.__table__])


def _SessionLocal():
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine

    return sessionmaker(bind=get_engine())


def submit_task(
    message: str,
    session_id: str | None = None,
    user_id: str = "default",
    owner_user_id: str | None = None,
) -> dict:
    """Enqueue chat task, return {task_id, status}. Eksekusi async."""
    from main import route_request

    if not owner_user_id:
        owner_user_id = user_id
    task_id = str(uuid.uuid4())
    sid = str(uuid.uuid4())

    _ensure_table()
    SessionLocal = _SessionLocal()

    # Per-user depth limit: tolak bila sudah terlalu banyak task aktif
    with SessionLocal() as db:
        from src.core.db.models import BackgroundTask

        active_count = (
            db.query(func.count())
            .filter(
                BackgroundTask.owner_user_id == owner_user_id,
                BackgroundTask.status.in_(["pending", "running"]),
            )
            .scalar()
        )
        if active_count >= _MAX_TASKS_PER_USER:
            return {
                "task_id": "",
                "status": "error",
                "detail": f"Batas task terlampaui (max {_MAX_TASKS_PER_USER} aktif per user).",
            }
    with SessionLocal() as db:
        from src.core.db.models import BackgroundTask

        task = BackgroundTask(
            id=task_id,
            kind="chat",
            status="pending",
            input=message[:2000],
            session_id=sid,
            owner_user_id=owner_user_id,
            user_id=user_id,
        )
        db.add(task)
        db.commit()

    def _run():
        SessionLocal2 = _SessionLocal()
        with SessionLocal2() as db:
            from src.core.db.models import BackgroundTask

            task = db.query(BackgroundTask).filter(BackgroundTask.id == task_id).first()
            if task:
                task.status = "running"
                db.commit()
            try:
                res = route_request(message, sid)
                if task:
                    task.status = "done"
                    task.result = _json.dumps(res, ensure_ascii=False)[:20000]
                    db.commit()
            except Exception as e:
                if task:
                    task.status = "error"
                    task.error = str(e)[:1000]
                    db.commit()

    import contextvars

    _ctx = contextvars.copy_context()
    _executor.submit(_ctx.run, _run)
    return {"task_id": task_id, "status": "pending", "session_id": sid}


def get_task(task_id: str, owner_user_id: str = "default") -> dict | None:
    _ensure_table()
    SessionLocal = _SessionLocal()
    with SessionLocal() as db:
        from src.core.db.models import BackgroundTask

        task = (
            db.query(BackgroundTask)
            .filter(BackgroundTask.id == task_id, BackgroundTask.owner_user_id == owner_user_id)
            .first()
        )
        if not task:
            return None
        out = {
            "task_id": task.id,
            "kind": task.kind,
            "status": task.status,
            "session_id": task.session_id,
            "owner_user_id": task.owner_user_id,
            "user_id": task.user_id,
            "error": task.error,
        }
        if task.result:
            try:
                out["result"] = _json.loads(task.result)
            except Exception as _e:
                logger.debug("task result JSON parse error: %s", _e)
                out["result"] = {"answer": task.result[:2000]}
        return out


def list_tasks(offset: int = 0, limit: int = 20, owner_user_id: str = "default") -> list:
    _ensure_table()
    SessionLocal = _SessionLocal()
    with SessionLocal() as db:
        from src.core.db.models import BackgroundTask

        rows = (
            db.query(BackgroundTask)
            .filter(BackgroundTask.owner_user_id == owner_user_id)
            .order_by(BackgroundTask.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            {
                "task_id": r.id,
                "kind": r.kind,
                "status": r.status,
                "session_id": r.session_id,
                "owner_user_id": r.owner_user_id,
            }
            for r in rows
        ]
