"""Cost/latency observability: catat metrik tiap request + token LLM best-effort.

Token dioper via ContextVar (tanpa ubah signature): jalur LLM memanggil
note_usage(response) seusai invoke; decorator record_usage membaca + reset.
Tabel: request_stats. Tak pernah gagalkan request (try/except di semua tulis).
"""

import functools
import time
from contextvars import ContextVar

_last_usage: ContextVar[dict | None] = ContextVar("llm_usage", default=None)


def note_usage(response) -> None:
    """Ekstrak token dari respons LangChain (usage_metadata / response_metadata)."""
    try:
        usage = getattr(response, "usage_metadata", None)
        if isinstance(usage, dict) and usage:
            _last_usage.set(
                {
                    "prompt_tokens": int(usage.get("input_tokens", 0) or 0),
                    "completion_tokens": int(usage.get("output_tokens", 0) or 0),
                    "total_tokens": int(usage.get("total_tokens", 0) or 0),
                }
            )
            return
        meta = getattr(response, "response_metadata", None) or {}
        tu = meta.get("token_usage") or {}
        if tu:
            _last_usage.set(
                {
                    "prompt_tokens": int(tu.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(tu.get("completion_tokens", 0) or 0),
                    "total_tokens": int(tu.get("total_tokens", 0) or 0),
                }
            )
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("note_usage error: %s", _e)


def pop_usage() -> dict:
    val = dict(_last_usage.get() or {})
    _last_usage.set({})
    return val


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS request_stats (
            id TEXT PRIMARY KEY,
            ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            session_id TEXT NOT NULL DEFAULT '',
            agent_type TEXT NOT NULL DEFAULT '',
            tools TEXT NOT NULL DEFAULT '',
            latency_s FLOAT NOT NULL DEFAULT 0,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            success BOOLEAN NOT NULL DEFAULT TRUE
        );
    """)


def _write_stats(
    session_id: str, result: dict, latency: float, success: bool, usage: dict
):
    try:
        from src.core.db.db import connect

        conn = connect()
        cur = conn.cursor()
        _ensure_table(cur)
        tools = ",".join(result.get("tools_used") or [])
        cur.execute(
            "INSERT INTO request_stats(session_id, agent_type, tools, latency_s,"
            " prompt_tokens, completion_tokens, total_tokens, success)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s);",
            (
                session_id,
                result.get("agent_type", ""),
                tools[:500],
                round(latency, 2),
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("total_tokens", 0),
                success,
            ),
        )
        conn.close()
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("_write_stats error: %s", _e)


def record_usage(fn):
    """Decorator untuk route_request: catat latensi/agent/tools/token/sukses."""

    @functools.wraps(fn)
    def wrapper(user_input: str, session_id: str, *args, **kwargs):
        t_start = time.time()
        try:
            result = fn(user_input, session_id, *args, **kwargs)
        except Exception:
            _write_stats(session_id, {}, time.time() - t_start, False, {})
            raise
        _write_stats(
            session_id,
            result if isinstance(result, dict) else {},
            time.time() - t_start,
            True,
            pop_usage(),
        )
        return result

    return wrapper


def summarize_usage(hours: int = 24) -> dict:
    """Agregat untuk GET /usage/summary."""
    from src.core.db.db import connect

    conn = connect()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute(
        "SELECT COUNT(*), AVG(latency_s), SUM(total_tokens), SUM(prompt_tokens), SUM(completion_tokens),"
        " SUM(CASE WHEN success THEN 1 ELSE 0 END) FROM request_stats"
        " WHERE ts > NOW() - (%s || ' hours')::INTERVAL;",
        (str(hours),),
    )
    n, avg_lat, tot, prm, cmp_, okc = cur.fetchone()
    cur.execute(
        "SELECT agent_type, COUNT(*), AVG(latency_s), SUM(total_tokens) FROM request_stats"
        " WHERE ts > NOW() - (%s || ' hours')::INTERVAL GROUP BY agent_type ORDER BY 2 DESC;",
        (str(hours),),
    )
    by_agent = [
        {
            "agent": r[0],
            "count": r[1],
            "avg_latency": round(float(r[2] or 0), 2),
            "tokens": int(r[3] or 0),
        }
        for r in cur.fetchall()
    ]
    conn.close()
    return {
        "hours": hours,
        "requests": int(n or 0),
        "success": int(okc or 0),
        "avg_latency_s": round(float(avg_lat or 0), 2),
        "total_tokens": int(tot or 0),
        "prompt_tokens": int(prm or 0),
        "completion_tokens": int(cmp_ or 0),
        "by_agent": by_agent,
    }
