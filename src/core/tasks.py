"""Async task queue: request lambat jadi background job.

POST /tasks → 202 {task_id}; worker thread-pool jalankan route_request;
GET /tasks/{id} untuk poll status + hasil. Tabel: background_tasks.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=4)
_lock = threading.Lock()


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS background_tasks (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL DEFAULT 'chat',
            status TEXT NOT NULL DEFAULT 'pending',
            input TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL DEFAULT '',
            owner_user_id TEXT NOT NULL,
            user_id TEXT NOT NULL DEFAULT 'default',
            result TEXT NULL,
            error TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    # Migration: add owner_user_id column if missing
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'background_tasks' AND column_name = 'owner_user_id'
            ) THEN
                ALTER TABLE background_tasks ADD COLUMN owner_user_id TEXT NOT NULL DEFAULT 'default';
            END IF;
        END $$;
    """)
    # Migration: add user_id column if missing
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'background_tasks' AND column_name = 'user_id'
            ) THEN
                ALTER TABLE background_tasks ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';
            END IF;
        END $$;
    """)


def _conn():
    from src.core.db import connect

    return connect()


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
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute(
        "INSERT INTO background_tasks(id, kind, status, input, session_id, owner_user_id, user_id)"
        " VALUES (%s, 'chat', 'pending', %s, %s, %s);",
        (task_id, message[:2000], sid, owner_user_id),
    )
    conn.close()

    def _run():
        import json as _json

        conn2 = _conn()
        cur2 = conn2.cursor()
        cur2.execute(
            "UPDATE background_tasks SET status='running', updated_at=NOW() WHERE id=%s;",
            (task_id,),
        )
        try:
            res = route_request(message, sid)
            cur2.execute(
                "UPDATE background_tasks SET status='done', result=%s, updated_at=NOW() WHERE id=%s;",
                (_json.dumps(res, ensure_ascii=False)[:20000], task_id),
            )
        except Exception as e:
            cur2.execute(
                "UPDATE background_tasks SET status='error', error=%s, updated_at=NOW() WHERE id=%s;",
                (str(e)[:1000], task_id),
            )
        conn2.close()

    import contextvars

    _ctx = contextvars.copy_context()
    _executor.submit(_ctx.run, _run)
    return {"task_id": task_id, "status": "pending", "session_id": sid}


def get_task(task_id: str, owner_user_id: str = "default") -> dict | None:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute(
        "SELECT id, kind, status, input, session_id, owner_user_id, user_id, result, error FROM background_tasks WHERE id = %s AND owner_user_id = %s;",
        (task_id, owner_user_id),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    import json as _json

    out = {
        "task_id": row[0],
        "kind": row[1],
        "status": row[2],
        "session_id": row[4],
        "owner_user_id": row[5],
        "user_id": row[6],
        "error": row[8],
    }
    if row[7]:
        try:
            out["result"] = _json.loads(row[7])
        except Exception as _e:
            import logging

            logging.getLogger(__name__).debug("task result JSON parse error: %s", _e)
            out["result"] = {"answer": row[7][:2000]}
    return out


def list_tasks(limit: int = 20, owner_user_id: str = "default") -> list:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute(
        "SELECT id, kind, status, session_id, owner_user_id FROM background_tasks WHERE owner_user_id = %s ORDER BY id DESC LIMIT %s;",
        (owner_user_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "task_id": r[0],
            "kind": r[1],
            "status": r[2],
            "session_id": r[3],
            "owner_user_id": r[4],
        }
        for r in rows
    ]
