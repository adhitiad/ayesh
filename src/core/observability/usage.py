"""Cost/latency observability: catat metrik tiap request + token LLM best-effort.

Token dioper via ContextVar (tanpa ubah signature): jalur LLM memanggil
note_usage(response) seusai invoke; decorator record_usage membaca + reset.
Tabel: request_stats. Tak pernah gagalkan request (try/except di semua tulis).
"""

import functools
import logging
import time
from contextvars import ContextVar

logger = logging.getLogger(__name__)

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
        logger.debug("note_usage error: %s", _e)


def pop_usage() -> dict:
    val = dict(_last_usage.get() or {})
    _last_usage.set({})
    return val


def _ensure_table(cur=None):
    """Ensure request_stats table exists. Accepts cursor (no-op) for backward compat."""
    from src.core.db.db_engine import get_engine
    from src.core.db.models import Base, RequestStat

    Base.metadata.create_all(get_engine(), tables=[RequestStat.__table__])


def _SessionLocal():
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine

    return sessionmaker(bind=get_engine())


def _write_stats(session_id: str, result: dict, latency: float, success: bool, usage: dict):
    try:
        _ensure_table()
        SessionLocal = _SessionLocal()
        tools = ",".join(result.get("tools_used") or [])
        with SessionLocal() as db:
            from src.core.db.models import RequestStat

            stat = RequestStat(
                session_id=session_id,
                agent_type=result.get("agent_type", ""),
                tools=tools[:500],
                latency_s=round(latency, 2),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                success=success,
            )
            db.add(stat)
            db.commit()
    except Exception as _e:
        logger.debug("_write_stats error: %s", _e)


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
    from sqlalchemy import func, text
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine
    from src.core.db.models import RequestStat

    _ensure_table()
    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        # Overall stats via raw SQL for accuracy
        hours_interval = text(f"'{hours} hours'")
        row = db.execute(
            text(
                "SELECT COUNT(*), AVG(latency_s), SUM(total_tokens), SUM(prompt_tokens), SUM(completion_tokens),"
                " SUM(CASE WHEN success THEN 1 ELSE 0 END) FROM request_stats"
                " WHERE ts > NOW() - :interval"
            ),
            {"interval": hours_interval},
        ).fetchone()
        n = row[0] if row else 0
        avg_lat = row[1] if row else 0
        tot = row[2] if row else 0
        prm = row[3] if row else 0
        cmp_ = row[4] if row else 0
        okc = row[5] if row else 0

        # By agent
        agent_rows = (
            db.query(
                RequestStat.agent_type,
                func.count(RequestStat.id),
                func.avg(RequestStat.latency_s),
                func.sum(RequestStat.total_tokens),
            )
            .filter(RequestStat.ts > func.now() - text(f" INTERVAL '{hours} hours'"))
            .group_by(RequestStat.agent_type)
            .order_by(func.count(RequestStat.id).desc())
            .all()
        )
        by_agent = [
            {
                "agent": r[0],
                "count": r[1],
                "avg_latency": round(float(r[2] or 0), 2),
                "tokens": int(r[3] or 0),
            }
            for r in agent_rows
        ]

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
