from fastapi import APIRouter
from fastapi import Request, HTTPException
from src.core.auth import require_auth, require_admin, require_owner
from src.core.observability import health_check, get_metrics
from src.core.analytics import generate_report
from src.core.audit import verify_audit_chain
from src.core.usage import summarize_usage
from src.core.db import connect
from src.core.usage import _ensure_table
from src.config.routing_keywords_pg import get_routing_keywords
from sqlalchemy.orm import sessionmaker
from src.core.models import Feedback, SessionMemory, LogEntry, Session
from src.core.db_engine import get_engine
from datetime import datetime

router = APIRouter()

_SessionLocal = sessionmaker(bind=get_engine())


@router.get("/health")
def health():
    h = health_check()
    return {
        "postgres": {
            "status": "up" if h.postgres else "down",
            "latency_ms": round(h.db_latency_ms, 2),
        },
        "redis": {
            "status": "up" if h.redis else "down",
            "latency_ms": round(h.redis_latency_ms, 2),
        },
    }


@router.get("/metrics")
def metrics():
    return get_metrics()


@router.get("/analytics")
def analytics(request: Request):
    require_admin(request)
    return generate_report()


@router.get("/audit")
def list_audit(request: Request, limit: int = 50):
    require_admin(request)
    conn = connect()
    cur = conn.cursor()
    from src.core.audit import _ensure_table

    _ensure_table(cur)
    conn.commit()
    cur.execute(
        "SELECT id, ts, actor, action, details, hash FROM audit_log ORDER BY id DESC LIMIT %s;",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "ts": str(r[1]),
            "actor": r[2],
            "action": r[3],
            "details": (r[4] or "")[:300],
            "hash": r[5][:16],
        }
        for r in rows
    ]


@router.get("/audit/verify")
def verify_audit(request: Request):
    require_admin(request)
    return verify_audit_chain()


@router.get("/usage/summary")
def usage_summary(request: Request, hours: int = 24):
    require_admin(request)
    return summarize_usage(hours=hours)


@router.get("/usage/recent")
def usage_recent(request: Request, limit: int = 20):
    require_admin(request)
    conn = connect()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute(
        "SELECT ts, session_id, agent_type, tools, latency_s, total_tokens, success FROM request_stats ORDER BY id DESC LIMIT %s;",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "ts": str(r[0]),
            "session": r[1],
            "agent": r[2],
            "tools": r[3],
            "latency_s": r[4],
            "tokens": r[5],
            "ok": r[6],
        }
        for r in rows
    ]


@router.get("/feedback/stats")
def feedback_stats(request: Request):
    require_admin(request)
    with _SessionLocal() as db:
        results = db.execute(
            select(
                Feedback.agent_type, func.avg(Feedback.rating), func.count()
            ).group_by(Feedback.agent_type)
        ).all()
    stats = {}
    for agent, avg_rating, count in results:
        stats[agent] = {"avg_rating": round(float(avg_rating), 2), "total": count}
    return stats


@router.get("/feedback/recent")
def feedback_recent(request: Request, limit: int = 10):
    require_admin(request)
    with _SessionLocal() as db:
        results = (
            db.execute(
                select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
            )
            .scalars()
            .all()
        )
    return [
        {
            "session_id": r.session_id,
            "agent_type": r.agent_type,
            "rating": r.rating,
            "comment": r.comment,
            "created_at": str(r.created_at),
        }
        for r in results
    ]


@router.get("/sessions")
def list_sessions(request: Request, limit: int = 50):
    owner_user_id = require_auth(request)
    with _SessionLocal() as db:
        sessions = (
            db.query(Session)
            .filter(Session.owner_user_id == owner_user_id)
            .order_by(Session.created_at.desc())
            .limit(limit)
            .all()
        )
    return [
        {
            "id": s.id,
            "user_id": s.user_id,
            "nama": s.nama,
            "context": s.context,
            "agent_type": s.agent_type,
            "created_at": str(s.created_at),
            "updated_at": str(s.updated_at),
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
def get_session(request: Request, session_id: str):
    with _SessionLocal() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan")
    require_owner(request, sess.owner_user_id)
    return {
        "id": sess.id,
        "owner_user_id": sess.owner_user_id,
        "user_id": sess.user_id,
        "nama": sess.nama,
        "context": sess.context,
        "agent_type": sess.agent_type,
        "created_at": str(sess.created_at),
        "updated_at": str(sess.updated_at),
    }


@router.put("/sessions/{session_id}")
def update_session_info(
    request: Request,
    session_id: str,
    nama: str = None,
    context: str = None,
):
    with _SessionLocal() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
        if not sess:
            raise HTTPException(status_code=404, detail="Session tidak ditemukan")
        require_owner(request, sess.owner_user_id)
        if nama is not None:
            sess.nama = nama
        if context is not None:
            sess.context = context
        sess.updated_at = datetime.utcnow()
        db.commit()
    return {"status": "ok", "session_id": session_id}


@router.get("/sessions/{session_id}/chat")
def get_session_chat(request: Request, session_id: str, limit: int = 50):
    with _SessionLocal() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
        if not sess:
            raise HTTPException(status_code=404, detail="Session tidak ditemukan")
        require_owner(request, sess.owner_user_id)

        messages = (
            db.query(SessionMemory)
            .filter(SessionMemory.session_id == session_id)
            .order_by(SessionMemory.timestamp.desc())
            .limit(limit)
            .all()
        )

    history = []
    for msg in reversed(messages):
        history.append(
            {"role": msg.role, "content": msg.content, "timestamp": str(msg.timestamp)}
        )

    return {
        "session_id": session_id,
        "nama": sess.nama,
        "context": sess.context,
        "agent_type": sess.agent_type,
        "total_messages": len(history),
        "messages": history,
    }


@router.get("/memory/{session_id}")
def get_memory(request: Request, session_id: str, limit: int = 50):
    with _SessionLocal() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
        if not sess:
            raise HTTPException(status_code=404, detail="Session tidak ditemukan")
        require_owner(request, sess.owner_user_id)
        results = (
            db.execute(
                select(SessionMemory)
                .where(SessionMemory.session_id == session_id)
                .order_by(SessionMemory.timestamp.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
    return [
        {"role": r.role, "content": r.content[:200], "timestamp": str(r.timestamp)}
        for r in results
    ]


@router.delete("/memory/{session_id}")
def clear_memory(request: Request, session_id: str):
    with _SessionLocal() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
        if not sess:
            raise HTTPException(status_code=404, detail="Session tidak ditemukan")
        require_owner(request, sess.owner_user_id)
        db.execute(delete(SessionMemory).where(SessionMemory.session_id == session_id))
        db.commit()
    return {"status": "cleared", "session_id": session_id}


@router.get("/logs")
def get_logs(request: Request, level: str = None, limit: int = 50):
    require_admin(request)
    with _SessionLocal() as db:
        stmt = select(LogEntry).order_by(LogEntry.timestamp.desc()).limit(limit)
        if level:
            stmt = (
                select(LogEntry)
                .where(LogEntry.level == level.upper())
                .order_by(LogEntry.timestamp.desc())
                .limit(limit)
            )
        results = db.execute(stmt).scalars().all()
    return [
        {
            "logger_name": r.logger_name,
            "level": r.level,
            "message": r.message[:200],
            "timestamp": str(r.timestamp),
        }
        for r in results
    ]


@router.delete("/logs")
def clear_logs(request: Request):
    require_admin(request)
    with _SessionLocal() as db:
        db.execute(delete(LogEntry))
        db.commit()
    return {"status": "cleared"}


@router.get("/keywords")
def get_keywords(request: Request):
    require_admin(request)
    kws, default = get_routing_keywords()
    return {"keywords": kws, "default_agent": default}
