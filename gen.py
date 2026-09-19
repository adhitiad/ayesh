import os

# Fix api_server.py - export models for backward compatibility
content = '''from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.db_engine import get_engine
from src.core.observability import health_check, get_metrics
from src.config.rules import SUBAGENTS
from src.api.routes import (
    chat, feedback, agents, jobs, tasks,
    approvals, system
)
from src.api.middleware import setup_middleware
from src.core.scheduler import start_scheduler

# Export models for backward compatibility
from src.api.models import ChatRequest, FeedbackRequest, TaskRequest, UserRequest, JobRequest

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

app.include_router(chat.router)
app.include_router(feedback.router)
app.include_router(agents.router)
app.include_router(jobs.router)
app.include_router(tasks.router)
app.include_router(approvals.router)
app.include_router(system.router)

if __name__ == "__main__":
    import uvicorn
    _host = os.getenv("API_HOST", "127.0.0.1")
    _port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run(app, host=_host, port=_port)
'''

with open(r'E:\code\fr\api_server.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('api_server.py fixed')
