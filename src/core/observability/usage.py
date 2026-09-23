"""Cost/latency observability: catat metrik tiap request + token LLM best-effort.

Token dioper via ContextVar (tanpa ubah signature): jalur LLM memanggil
note_usage(response) seusai invoke; decorator record_usage membaca + reset.
Tabel: request_stats. Tak pernah gagalkan request (try/except di semua tulis).
"""

import functools
import logging
import threading
import time
from contextvars import ContextVar

logger = logging.getLogger(__name__)

_last_usage: ContextVar[dict | None] = ContextVar("llm_usage", default=None)

_cost_columns_lock = threading.Lock()
_cost_columns_ensured = False


def _note_model(data: dict, response) -> None:
    """Ambil nama model dari respons (response_metadata / atribut model)."""
    meta = getattr(response, "response_metadata", None) or {}
    model = meta.get("model_name") or meta.get("model") or ""
    if not model:
        model = getattr(response, "model", None) or ""
    if model:
        data["model"] = str(model)


def _extract_tokens(response) -> dict:
    """Token dari usage_metadata/response_metadata; tanpa token → data kosong."""
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        return {
            "prompt_tokens": int(usage.get("input_tokens", 0) or 0),
            "completion_tokens": int(usage.get("output_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
        }
    meta = getattr(response, "response_metadata", None) or {}
    tu = meta.get("token_usage") or {}
    if tu:
        return {
            "prompt_tokens": int(tu.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(tu.get("completion_tokens", 0) or 0),
            "total_tokens": int(tu.get("total_tokens", 0) or 0),
        }
    # Tanpa info token: catat model saja bila teridentifikasi (cost = 0).
    model = meta.get("model_name") or meta.get("model") or getattr(response, "model", None) or ""
    if model:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {}


def note_usage(response) -> None:
    """Ekstrak token + model dari respons LangChain dan simpan ke ContextVar."""
    try:
        data = _extract_tokens(response)
        _note_model(data, response)
        if data:
            _last_usage.set(data)
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


def _ensure_cost_columns() -> None:
    """Lazy-ALTER kolom model/cost_usd untuk instalasi dengan tabel lama."""
    global _cost_columns_ensured
    if _cost_columns_ensured:
        return
    with _cost_columns_lock:
        if _cost_columns_ensured:
            return
        try:
            from sqlalchemy import inspect, text

            from src.core.db.db_engine import get_engine

            with get_engine().connect() as con:
                has = {c["name"] for c in inspect(con).get_columns("request_stats")}
                wanted = {
                    "model": "VARCHAR(100) NOT NULL DEFAULT ''",
                    "cost_usd": "NUMERIC(12,6)",
                    "user_id": "VARCHAR(36)",
                }
                for col, ddl in wanted.items():
                    if col not in has:
                        con.execute(text(f"ALTER TABLE request_stats ADD COLUMN {col} {ddl}"))
                con.commit()
        except Exception as _e:
            # Gagal menambah kolom tidak boleh menggagalkan request.
            logger.warning("_ensure_cost_columns error: %s", _e)
        finally:
            _cost_columns_ensured = True


def _SessionLocal():
    from src.core.db.db_engine import get_session

    return get_session()


def _write_stats(session_id: str, result: dict, latency: float, success: bool, usage: dict, user_id: str | None = None):
    try:
        _ensure_table()
        _ensure_cost_columns()
        SessionLocal = _SessionLocal()
        tools = ",".join(result.get("tools_used") or [])
        model = (usage.get("model") or "").strip()[:100]
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        with SessionLocal() as db:
            from src.core.db.models import RequestStat
            from src.core.observability.pricing import estimate_cost_usd

            stat = RequestStat(
                session_id=session_id,
                user_id=user_id,
                agent_type=result.get("agent_type", ""),
                tools=tools[:500],
                latency_s=round(latency, 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=usage.get("total_tokens", 0),
                success=success,
                model=model,
                cost_usd=estimate_cost_usd(model, prompt_tokens, completion_tokens),
            )
            db.add(stat)
            db.commit()
    except Exception as _e:
        logger.debug("_write_stats error: %s", _e)


def record_usage(fn):
    """Decorator untuk route_request: catat latensi/agent/tools/token/sukses."""

    @functools.wraps(fn)
    def wrapper(user_input: str, session_id: str, *args, **kwargs):
        from src.core.auth.auth import get_current_user_id

        uid = get_current_user_id()
        t_start = time.time()
        try:
            result = fn(user_input, session_id, *args, **kwargs)
        except Exception:
            _write_stats(session_id, {}, time.time() - t_start, False, {}, user_id=uid)
            raise
        _write_stats(
            session_id,
            result if isinstance(result, dict) else {},
            time.time() - t_start,
            True,
            pop_usage(),
            user_id=uid,
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
    _ensure_cost_columns()
    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        # Overall stats via raw SQL for accuracy
        row = db.execute(
            text(
                "SELECT COUNT(*), AVG(latency_s), SUM(total_tokens), SUM(prompt_tokens), SUM(completion_tokens),"
                " SUM(CASE WHEN success THEN 1 ELSE 0 END), SUM(cost_usd) FROM request_stats"
                " WHERE ts > NOW() - make_interval(hours => :hours)"
            ),
            {"hours": int(hours)},
        ).fetchone()
        n = row[0] if row else 0
        avg_lat = row[1] if row else 0
        tot = row[2] if row else 0
        prm = row[3] if row else 0
        cmp_ = row[4] if row else 0
        okc = row[5] if row else 0
        cost = row[6] if row else 0

        # By agent
        agent_rows = (
            db.query(
                RequestStat.agent_type,
                func.count(RequestStat.id),
                func.avg(RequestStat.latency_s),
                func.sum(RequestStat.total_tokens),
            )
            .filter(RequestStat.ts > func.now() - text("make_interval(hours => :hours)"), {"hours": int(hours)})
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
        "estimated_cost_usd": round(float(cost or 0), 6),
        "by_agent": by_agent,
    }


def summarize_user_usage(uid: str, hours: int = 24) -> dict:
    """Agregat usage per-user untuk GET /usage/user/{uid}."""
    from sqlalchemy import func, text

    from src.core.db.db_engine import get_session
    from src.core.db.models import RequestStat

    _ensure_table()
    _ensure_cost_columns()
    with get_session() as db:
        row = db.execute(
            text(
                "SELECT COUNT(*), AVG(latency_s), SUM(total_tokens), SUM(prompt_tokens), SUM(completion_tokens),"
                " SUM(CASE WHEN success THEN 1 ELSE 0 END), SUM(cost_usd) FROM request_stats"
                " WHERE user_id = :uid AND ts > NOW() - make_interval(hours => :hours)"
            ),
            {"uid": uid, "hours": int(hours)},
        ).fetchone()
        n = row[0] if row else 0
        avg_lat = row[1] if row else 0
        tot = row[2] if row else 0
        prm = row[3] if row else 0
        cmp_ = row[4] if row else 0
        okc = row[5] if row else 0
        cost = row[6] if row else 0

        agent_rows = (
            db.query(
                RequestStat.agent_type,
                func.count(RequestStat.id),
                func.sum(RequestStat.total_tokens),
            )
            .filter(
                RequestStat.user_id == uid,
                RequestStat.ts > func.now() - text("make_interval(hours => :hours)"),
            )
            .group_by(RequestStat.agent_type)
            .order_by(func.count(RequestStat.id).desc())
            .all()
        )
        by_agent = [{"agent": r[0], "count": r[1], "tokens": int(r[2] or 0)} for r in agent_rows]

    return {
        "user_id": uid,
        "hours": hours,
        "requests": int(n or 0),
        "success": int(okc or 0),
        "avg_latency_s": round(float(avg_lat or 0), 2),
        "total_tokens": int(tot or 0),
        "prompt_tokens": int(prm or 0),
        "completion_tokens": int(cmp_ or 0),
        "estimated_cost_usd": round(float(cost or 0), 6),
        "by_agent": by_agent,
    }
