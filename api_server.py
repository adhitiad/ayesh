from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.observability import health_check, get_metrics
from core.models_feedback import Feedback
from core.models import SessionMemory, LogEntry
from sqlalchemy import create_engine, select, func, delete
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

app = FastAPI(
    title="Multi-Agent AI Orchestrator API",
    version="2.0",
    description="Health check, feedback, memory, logs, dan metrics"
)

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

@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    if not (1 <= req.rating <= 5):
        raise HTTPException(status_code=400, detail="rating harus 1-5")
    with SessionLocal() as db:
        fb = Feedback(session_id=req.session_id, agent_type=req.agent_type, rating=req.rating, comment=req.comment)
        db.add(fb)
        db.commit()
    return {"status": "ok", "rating": req.rating, "agent_type": req.agent_type}

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
