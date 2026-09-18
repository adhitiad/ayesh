"""Human-in-the-loop approval: tool berbahaya jeda minta persetujuan.

Aktif hanya bila env REQUIRE_APPROVAL=1 (default mati agar eval/tes tak macet).
Session scheduler (prefix "job_") auto-approve agar job otonom tidak gantung.
Tool menunggu max APPROVAL_TIMEOUT_S (default 600); deny/timeout → tool
mengembalikan pesan error (agent tetap hidup menjelaskan ke user).

Gate (should_gate): jalankan_python selalu; panggil_mcp selalu;
tulis_kode hanya bila overwrite=True.
"""

import os
import time
import uuid
from contextvars import ContextVar

current_session: ContextVar[str] = ContextVar("approval_session", default="")


def set_current_session(session_id: str) -> None:
    current_session.set(session_id or "")


def approval_required() -> bool:
    return os.getenv("REQUIRE_APPROVAL", "0") == "1"


def approval_timeout() -> int:
    try:
        return max(5, int(os.getenv("APPROVAL_TIMEOUT_S", "600")))
    except ValueError:
        return 600


def should_gate(tool_name: str, args: dict) -> bool:
    """Pure: apakah pemanggilan ini perlu approval? (tanpa DB, testable)."""
    args = args or {}
    if tool_name == "jalankan_python":
        return True
    if tool_name == "panggil_mcp":
        return True
    if tool_name == "tulis_kode" and args.get("overwrite") is True:
        return True
    return False


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_approvals (
            id TEXT PRIMARY KEY,
            tool TEXT NOT NULL,
            args TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_at TIMESTAMPTZ NULL
        );
    """)


def _conn():
    from core.db import connect
    return connect()


def request_approval(tool_name: str, args: dict, timeout_s: int | None = None) -> tuple[bool, str]:
    """Minta approval, blokir hingga diputus/timeout. Return (approved, approval_id)."""
    import json as _json
    session_id = current_session.get()
    if session_id.startswith("job_"):
        return True, "auto-approved-job"
    timeout_s = timeout_s or approval_timeout()
    aid = f"appr_{uuid.uuid4().hex[:8]}"
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute(
        "INSERT INTO pending_approvals(id, tool, args, session_id) VALUES (%s, %s, %s, %s);",
        (aid, tool_name, _json.dumps(args, ensure_ascii=False)[:2000], session_id),
    )
    conn.close()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(5)
        conn2 = _conn()
        cur2 = conn2.cursor()
        cur2.execute("SELECT status FROM pending_approvals WHERE id = %s;", (aid,))
        row = cur2.fetchone()
        conn2.close()
        if row and row[0] == "approved":
            return True, aid
        if row and row[0] == "denied":
            return False, aid
    conn3 = _conn()
    cur3 = conn3.cursor()
    cur3.execute("UPDATE pending_approvals SET status='expired', decided_at=NOW() WHERE id=%s AND status='pending';", (aid,))
    conn3.close()
    return False, aid


def ensure_approved(tool_name: str, args: dict) -> tuple[bool, str]:
    """Gate utama dipanggil dari tool. Return (boleh_lanjut, pesan)."""
    if not approval_required():
        return True, ""
    if not should_gate(tool_name, args):
        return True, ""
    ok, aid = request_approval(tool_name, args)
    if ok:
        return True, ""
    return False, (f"Aksi {tool_name} DITOLAK/timeout (approval {aid}). "
                   "Jelaskan ke user dan tawarkan alternatif aman.")


def list_pending() -> list:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT id, tool, args, session_id, created_at FROM pending_approvals WHERE status='pending' ORDER BY id;")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "tool": r[1], "args": (r[2] or "")[:500], "session": r[3], "created": str(r[4])} for r in rows]


def decide(aid: str, approved: bool) -> bool:
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute("UPDATE pending_approvals SET status=%s, decided_at=NOW() WHERE id=%s AND status='pending';",
                ("approved" if approved else "denied", aid))
    n = cur.rowcount
    conn.close()
    return n > 0
