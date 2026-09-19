import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.db_engine import get_engine
from src.core.observability import health_check, get_metrics
from src.config.rules import SUBAGENTS
from src.api.routes import chat, feedback, agents, jobs, tasks, approvals, system
from src.api.routes_chat import router as chat_router
from src.api.routes_feedback import router as feedback_router
from src.api.routes_agents import router as agents_router
from src.api.routes_jobs import router as jobs_router
from src.api.routes_tasks import router as tasks_router
from src.api.routes_approvals import router as approvals_router
from src.api.routes_system import router as system_router
from src.api.middleware import setup_middleware
from src.core.scheduler import start_scheduler

# Export models for backward compatibility
from src.api.models import (
    ChatRequest,
    FeedbackRequest,
    TaskRequest,
    UserRequest,
    JobRequest,
)
from src.api.routes_agents import create_user_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("ENABLE_SCHEDULER", "0") == "1":
        start_scheduler()
    yield


app = FastAPI(
    title="Ayesh — Multi-Agent AI Orchestrator API",
    version="2.0",
    description="Health check, feedback, memory, logs, metrics, dan chat",
    lifespan=lifespan,
)

# P3.4 — CORS: explicit allowlist (never * with credentials)
_allowed_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization"],
    max_age=600,
)

setup_middleware(app)

app.include_router(chat_router)
app.include_router(feedback_router)
app.include_router(agents_router)
app.include_router(jobs_router)
app.include_router(tasks_router)
app.include_router(approvals_router)
app.include_router(system_router)

if __name__ == "__main__":
    import uvicorn

    _host = os.getenv("API_HOST", "127.0.0.1")
    _port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run(app, host=_host, port=_port)
