from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import asyncio
import json
import os
import uuid
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from core.observability import health_check, get_metrics
from core.models import Feedback, SessionMemory, LogEntry, Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func, delete
from core.db_engine import get_engine
from main import route_request
from agents.agent_executor import run_agent_executor_stream
from mcp_core.registry import load_mcp_context
from core.adaptive_router import classify_agent
from plugins.input_guard import PromptInjectionGuardMiddleware

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("ENABLE_SCHEDULER", "0") == "1":
        from core.scheduler import start_scheduler
        start_scheduler()
    yield


app = FastAPI(
    title="Ayesh — Multi-Agent AI Orchestrator API",
    version="2.0",
    description="Health check, feedback, memory, logs, metrics, dan chat",
    lifespan=lifespan,
)

# Middleware: Prompt Injection Guard
app.add_middleware(PromptInjectionGuardMiddleware)

# Rate Limiter per IP (token bucket)
_ip_buckets: dict = defaultdict(lambda: {"tokens": 30, "last": time.time()})  # 30 req/min default
_ip_lock = asyncio.Lock()
MAX_REQ_PER_MIN = 30

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limit per IP: token bucket 30 req/menit."""
    if request.url.path in ["/chat", "/chat/stream", "/chat/stream/tokens"]:
        client_ip = request.client.host if request.client else "unknown"
        async with _ip_lock:
            bucket = _ip_buckets[client_ip]
            now = time.time()
            # Refill: 0.5 token per detik (30 per menit)
            elapsed = now - bucket["last"]
            bucket["tokens"] = min(30, bucket["tokens"] + elapsed * 0.5)
            bucket["last"] = now

            if bucket["tokens"] < 1:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={"error": "Rate limit exceeded", "detail": "Terlalu banyak request per menit. Coba lagi nanti.", "retry_after": int((1 - bucket["tokens"]) / 0.5) + 1}
                )
            bucket["tokens"] -= 1
    return await call_next(request)

# === Chat ===
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    """Terima pesan, route ke agent, return JSON."""
    from core.auth import bind_request_user
    bind_request_user(request)
    session_id = req.session_id or f"api_{uuid.uuid4().hex[:8]}"
    try:
        result = route_request(user_input=req.message, session_id=session_id)
        try:
            from core.audit import append_audit
            append_audit("chat", actor=session_id, details={"agent": result.get("agent_type"), "tools": result.get("tools_used", []), "msg": req.message[:200]})
        except Exception:
            pass
        return result
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "Too Many Requests" in error_msg:
            raise HTTPException(status_code=429, detail="LLM API rate limit terlampaui. Coba lagi dalam beberapa detik.")
        raise HTTPException(status_code=500, detail=f"Gagal memproses: {error_msg[:200]}")


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """SSE: event status → done (hasil JSON) / error. Ping tiap 15s selama menunggu."""
    from core.auth import bind_request_user
    bind_request_user(request)
    session_id = req.session_id or f"api_{uuid.uuid4().hex[:8]}"

    async def _gen():
        yield f"event: status\ndata: {json.dumps({'stage': 'routing', 'session_id': session_id})}\n\n"
        task = asyncio.create_task(asyncio.to_thread(route_request, req.message, session_id))
        while True:
            done, _ = await asyncio.wait({task}, timeout=15)
            if done:
                break
            yield ": ping\n\n"
        try:
            result = task.result()
            yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
        except Exception as e:
            msg = str(e)
            code = "rate_limited" if ("429" in msg or "Too Many Requests" in msg) else "error"
            yield f"event: error\ndata: {json.dumps({'code': code, 'detail': msg[:200]})}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/chat/stream/tokens")
async def chat_stream_tokens(req: ChatRequest, request: Request):
    """SSE token-level: stream token demi token dari LLM."""
    from core.auth import bind_request_user
    bind_request_user(request)
    session_id = req.session_id or f"api_{uuid.uuid4().hex[:8]}"
    user_input = req.message

    # Routing & prompt building (sync, cepat)
    agent_type = classify_agent(user_input, user_id=session_id)
    system_prompt, default_tools = load_mcp_context(
        agent_type,
        session_nama=None,
        session_context=None,
    )
    from mcp_core.skills import get_skills_block
    skill_block = get_skills_block()
    augmented_prompt = system_prompt + skill_block
    # Preferensi
    try:
        from plugins.core_tools import get_preferences_block
        _pref_block = get_preferences_block()
        if _pref_block:
            augmented_prompt += f"\n\n## {_pref_block}"
    except Exception:
        pass
    from mcp_core.tool_validator import validate_tools_for_agent
    filtered_tools = default_tools
    validated_tools = validate_tools_for_agent(agent_type, filtered_tools)

    async def _gen():
        yield f"event: status\ndata: {json.dumps({'stage': 'streaming', 'agent': agent_type, 'session_id': session_id})}\n\n"
        try:
            async for token in run_agent_executor_stream(
                user_input=user_input,
                session_id=session_id,
                system_prompt=augmented_prompt,
                tools=validated_tools,
                context="",
            ):
                if token:
                    yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"
        except Exception as e:
            msg = str(e)
            code = "rate_limited" if ("429" in msg or "Too Many Requests" in msg) else "error"
            yield f"event: error\ndata: {json.dumps({'code': code, 'detail': msg[:200]})}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")

# === Sessions ===
@app.get("/sessions")
def list_sessions(limit: int = 50):
    """Daftar semua session."""
    with SessionLocal() as db:
        sessions = db.query(Session).order_by(Session.created_at.desc()).limit(limit).all()
    return [{"id": s.id, "nama": s.nama, "context": s.context, "agent_type": s.agent_type, "created_at": str(s.created_at), "updated_at": str(s.updated_at)} for s in sessions]

@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    """Detail satu session."""
    with SessionLocal() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan")
    return {"id": sess.id, "nama": sess.nama, "context": sess.context, "agent_type": sess.agent_type, "created_at": str(sess.created_at), "updated_at": str(sess.updated_at)}

@app.put("/sessions/{session_id}")
def update_session_info(session_id: str, nama: Optional[str] = None, context: Optional[str] = None):
    """Update nama/context session."""
    from datetime import datetime
    with SessionLocal() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
        if not sess:
            raise HTTPException(status_code=404, detail="Session tidak ditemukan")
        if nama is not None:
            sess.nama = nama
        if context is not None:
            sess.context = context
        sess.updated_at = datetime.utcnow()
        db.commit()
    return {"status": "ok", "session_id": session_id}

@app.get("/sessions/{session_id}/chat")
def get_session_chat(session_id: str, limit: int = 50):
    """Ambil history chat untuk session tertentu."""
    with SessionLocal() as db:
        # Cek session ada
        sess = db.query(Session).filter(Session.id == session_id).first()
        if not sess:
            raise HTTPException(status_code=404, detail="Session tidak ditemukan")
        
        # Ambil messages dari PostgreSQL
        messages = db.query(SessionMemory).filter(
            SessionMemory.session_id == session_id
        ).order_by(SessionMemory.timestamp.desc()).limit(limit).all()
    
    # Format response
    history = []
    for msg in reversed(messages):  # Reverse agar chronologis
        history.append({
            "role": msg.role,
            "content": msg.content,
            "timestamp": str(msg.timestamp)
        })
    
    return {
        "session_id": session_id,
        "nama": sess.nama,
        "context": sess.context,
        "agent_type": sess.agent_type,
        "total_messages": len(history),
        "messages": history
    }

# === Health ===
@app.get("/health")
def health():
    h = health_check()
    return {
        "postgres": {"status": "up" if h.postgres else "down", "latency_ms": round(h.db_latency_ms, 2)},
        "redis": {"status": "up" if h.redis else "down", "latency_ms": round(h.redis_latency_ms, 2)}
    }

# === Metrics ===
@app.get("/metrics")
def metrics():
    return get_metrics()

# === Feedback ===
class FeedbackRequest(BaseModel):
    session_id: str
    agent_type: str
    rating: int
    comment: Optional[str] = ""
    corrected_agent: Optional[str] = None

@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    if not (1 <= req.rating <= 5):
        raise HTTPException(status_code=400, detail="rating harus 1-5")
    if req.corrected_agent and req.corrected_agent not in {"coder_agent", "admin_agent", "casual_agent"}:
        raise HTTPException(status_code=400, detail="corrected_agent harus: coder_agent, admin_agent, atau casual_agent")
    with SessionLocal() as db:
        fb = Feedback(
            session_id=req.session_id,
            agent_type=req.agent_type,
            rating=req.rating,
            comment=req.comment,
            corrected_agent=req.corrected_agent,
        )
        db.add(fb)
        db.commit()
    # Trigger learning dari feedback
    if req.corrected_agent or req.rating <= 2:
        from main import _learn_from_feedback
        _learn_from_feedback(
            session_id=req.session_id,
            user_input=req.comment or "",
            agent_type=req.agent_type,
            rating=req.rating,
            corrected_agent=req.corrected_agent,
        )
    try:
        from core.audit import append_audit
        append_audit("feedback", actor=req.session_id, details={"agent": req.agent_type, "rating": req.rating, "corrected": req.corrected_agent})
    except Exception:
        pass
    return {"status": "ok", "rating": req.rating, "agent_type": req.agent_type, "learned": bool(req.corrected_agent or req.rating <= 2)}


# === Audit (tamper-proof hash chain) ===
@app.get("/audit")
def list_audit(limit: int = 50):
    from core.db import connect
    from core.audit import _ensure_table
    conn = connect()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT id, ts, actor, action, details, hash FROM audit_log ORDER BY id DESC LIMIT %s;", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "ts": str(r[1]), "actor": r[2], "action": r[3], "details": (r[4] or "")[:300], "hash": r[5][:16]} for r in rows]


@app.get("/audit/verify")
def verify_audit():
    from core.audit import verify_audit_chain
    return verify_audit_chain()


# === Analytics (failure/learnings/feedback/errors) ===
@app.get("/analytics")
def analytics():
    from core.analytics import generate_report
    return generate_report()


# === Background Tasks (async queue) ===
class TaskRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

@app.post("/tasks", status_code=202)
def submit_task(req: TaskRequest, request: Request):
    from core.tasks import submit_task
    from core.auth import bind_request_user
    bind_request_user(request)
    return submit_task(req.message, req.session_id)

@app.get("/tasks")
def list_tasks_endpoint(limit: int = 20):
    from core.tasks import list_tasks
    return list_tasks(limit=limit)

@app.get("/tasks/{task_id}")
def get_task_endpoint(task_id: str):
    from core.tasks import get_task
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    return task


# === Approvals (human-in-the-loop) ===
@app.get("/approvals/pending")
def approvals_pending():
    from core.approval import list_pending
    return list_pending()

@app.post("/approvals/{aid}/approve")
def approval_approve(aid: str):
    from core.approval import decide
    if not decide(aid, True):
        raise HTTPException(status_code=404, detail="Approval tidak ditemukan/sudah diputus")
    return {"status": "approved", "id": aid}

@app.post("/approvals/{aid}/deny")
def approval_deny(aid: str):
    from core.approval import decide
    if not decide(aid, False):
        raise HTTPException(status_code=404, detail="Approval tidak ditemukan/sudah diputus")
    return {"status": "denied", "id": aid}


# === Users (multi-user API keys) ===
class UserRequest(BaseModel):
    name: str

@app.post("/users")
def create_user_endpoint(req: UserRequest):
    from core.auth import create_user
    user = create_user(req.name)
    user["warning"] = "Simpan api_key sekarang — tidak ditampilkan lagi."
    return user

@app.get("/users")
def list_users_endpoint():
    from core.auth import list_users
    return list_users()

@app.delete("/users/{uid}")
def delete_user_endpoint(uid: int):
    from core.auth import deactivate_user
    if not deactivate_user(uid):
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return {"status": "deactivated", "id": uid}


# === Usage (cost/latency observability) ===
@app.get("/usage/summary")
def usage_summary(hours: int = 24):
    from core.usage import summarize_usage
    return summarize_usage(hours=hours)


@app.get("/usage/recent")
def usage_recent(limit: int = 20):
    from core.db import connect
    from core.usage import _ensure_table
    conn = connect()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT ts, session_id, agent_type, tools, latency_s, total_tokens, success FROM request_stats ORDER BY id DESC LIMIT %s;", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"ts": str(r[0]), "session": r[1], "agent": r[2], "tools": r[3], "latency_s": r[4], "tokens": r[5], "ok": r[6]} for r in rows]


# === Scheduled Jobs ===
class JobRequest(BaseModel):
    name: str
    prompt: str
    interval_detik: Optional[int] = None
    daily_at: Optional[str] = None  # "HH:MM" WIB

@app.post("/jobs")
def create_job_endpoint(req: JobRequest):
    from core.scheduler import create_job
    try:
        return create_job(req.name, req.prompt, req.interval_detik, req.daily_at)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/jobs")
def list_jobs_endpoint():
    from core.scheduler import list_jobs
    return list_jobs()

@app.delete("/jobs/{job_id}")
def delete_job_endpoint(job_id: int):
    from core.scheduler import delete_job
    if not delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return {"status": "deleted", "id": job_id}

@app.patch("/jobs/{job_id}")
def toggle_job_endpoint(job_id: int, enabled: bool = True):
    from core.scheduler import set_enabled
    if not set_enabled(job_id, enabled):
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return {"status": "ok", "id": job_id, "enabled": enabled}

@app.post("/jobs/{job_id}/run")
def run_job_once(job_id: int):
    from core.scheduler import list_jobs
    jobs = [j for j in list_jobs() if j["id"] == job_id]
    if not jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    # Ambil prompt penuh dari DB lalu eksekusi sekali
    from core.db import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT prompt, session_id FROM scheduled_jobs WHERE id = %s;", (job_id,))
    row = cur.fetchone()
    conn.close()
    try:
        result = route_request(row[0], row[1])
        return {"status": "ok", "id": job_id, "agent": result.get("agent_type")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menjalankan job: {str(e)[:200]}")

@app.get("/feedback/stats")
def feedback_stats():
    with SessionLocal() as db:
        results = db.execute(
            select(Feedback.agent_type, func.avg(Feedback.rating), func.count())
            .group_by(Feedback.agent_type)
        ).all()
    stats = {}
    for agent, avg_rating, count in results:
        stats[agent] = {"avg_rating": round(float(avg_rating), 2), "total": count}
    return stats

@app.get("/feedback/recent")
def feedback_recent(limit: int = 10):
    with SessionLocal() as db:
        results = db.execute(
            select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
        ).scalars().all()
    return [{"session_id": r.session_id, "agent_type": r.agent_type, "rating": r.rating, "comment": r.comment, "created_at": str(r.created_at)} for r in results]

# === Memory ===
@app.get("/memory/{session_id}")
def get_memory(session_id: str, limit: int = 50):
    with SessionLocal() as db:
        results = db.execute(
            select(SessionMemory).where(SessionMemory.session_id == session_id).order_by(SessionMemory.timestamp.desc()).limit(limit)
        ).scalars().all()
    return [{"role": r.role, "content": r.content[:200], "timestamp": str(r.timestamp)} for r in results]

@app.delete("/memory/{session_id}")
def clear_memory(session_id: str):
    with SessionLocal() as db:
        db.execute(delete(SessionMemory).where(SessionMemory.session_id == session_id))
        db.commit()
    return {"status": "cleared", "session_id": session_id}

# === Logs ===
@app.get("/logs")
def get_logs(level: Optional[str] = None, limit: int = 50):
    with SessionLocal() as db:
        stmt = select(LogEntry).order_by(LogEntry.timestamp.desc()).limit(limit)
        if level:
            stmt = select(LogEntry).where(LogEntry.level == level.upper()).order_by(LogEntry.timestamp.desc()).limit(limit)
        results = db.execute(stmt).scalars().all()
    return [{"logger_name": r.logger_name, "level": r.level, "message": r.message[:200], "timestamp": str(r.timestamp)} for r in results]

@app.delete("/logs")
def clear_logs():
    with SessionLocal() as db:
        db.execute(delete(LogEntry))
        db.commit()
    return {"status": "cleared"}

# === Routing Keywords ===
@app.get("/keywords")
def get_keywords():
    from config.routing_keywords_pg import get_routing_keywords
    kws, default = get_routing_keywords()
    return {"keywords": kws, "default_agent": default}

# === Agents & Skills (registry ala blok # Agents / # Skills Claude Code) ===
@app.get("/agents")
def list_agents():
    from config.rules import SUBAGENTS, AGENT_RULES
    return [
        {
            "name": name,
            "role": AGENT_RULES.get(name, {}).get("role", ""),
            "description": cfg.get("description", ""),
            "when_to_use": cfg.get("when_to_use", ""),
            "tools": cfg.get("tools", []),
        }
        for name, cfg in SUBAGENTS.items()
    ]

@app.get("/skills")
def list_skills_endpoint():
    from mcp_core.skills import list_skills
    return list_skills()

@app.get("/skills/{skill_name}")
def get_skill(skill_name: str):
    from mcp_core.skills import load_skill
    skill = load_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' tidak ditemukan")
    return skill

if __name__ == "__main__":
    import uvicorn
    _host = os.getenv("API_HOST", "127.0.0.1")
    _port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run(app, host=_host, port=_port)
