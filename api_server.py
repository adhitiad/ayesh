import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware import setup_middleware
from src.api.models import ChatRequest, FeedbackRequest, JobRequest, TaskRequest, UserRequest  # noqa: F401

# Export models for backward compatibility (tests import from api_server)
from src.api.routes_agents import create_user_endpoint  # noqa: F401
from src.api.routes_agents import router as agents_router
from src.api.routes_approvals import router as approvals_router
from src.api.routes_chat import router as chat_router
from src.api.routes_control import router as control_router
from src.api.routes_feedback import router as feedback_router
from src.api.routes_jobs import router as jobs_router
from src.api.routes_marketplace import router as marketplace_router
from src.api.routes_system import router as system_router
from src.api.routes_tasks import router as tasks_router
from src.api.routes_webhooks import router as webhooks_router
from src.config.rules import SUBAGENTS  # noqa: F401
from src.core.auth.auth_guards import effective_auth_config
from src.core.db.db_engine import get_engine  # noqa: F401
from src.core.observability.observability import get_metrics, health_check  # noqa: F401
from src.core.scheduler.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger(__name__).info("Auth effective config: %s", effective_auth_config())
    scheduler_started = False
    if os.getenv("ENABLE_SCHEDULER", "0") == "1":
        scheduler_started = start_scheduler()
    yield
    if scheduler_started:
        stop_scheduler()


app = FastAPI(
    title="Ayesh — Multi-Agent AI Orchestrator API",
    version="2.1",
    description="""## Authentication

Semua endpoint yang memerlukan auth mendukung **2 cara**:

### 1. X-API-Key (Header)
```
X-API-Key: fr_abc123def456...
```

### 2. Authorization Bearer (Header)
```
Authorization: Bearer fr_abc123def456...
```

> Register publik: `POST /users/register` → role=user (api_key sekali tampil).
> VIP $13.87: `POST /webhooks/vip-upgrade` (HMAC, idempotent) → role=vip.

## Roles
- **owner**: full — user manage (`GET /users`, `POST /users`, `DELETE /users/{id}`, `POST .../rotate`, `POST/DELETE .../vip`) + semua vip + semua self
- **vip**: paid $13.87/bulan — global (`keywords`, `templates`, `marketplace`, `audit`, `analytics`, `usage global`, `metrics`) + model manage self + premium models (`VIP_ONLY_MODELS`) + kuota longgar (`VIP_BURST/SUSTAINED`)
- **user**: chat, own sessions/memory/tasks/plans, own llm/mcp/skill configs, own usage (`/usage/me` self), katalog read; tidak dapat global vip

User manage hanya owner, model manage self/owner, global hanya vip (owner+vip).
""",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Chat", "description": "Chat dengan AI agent"},
        {"name": "Users", "description": "Manajemen user & API key (register/vip)"},
        {"name": "Jobs", "description": "Scheduled jobs (interval/harian)"},
        {"name": "Tasks", "description": "Async task queue"},
        {"name": "Sessions", "description": "Session & memory management"},
        {"name": "Feedback", "description": "Feedback & learning"},
        {"name": "System", "description": "Health, metrics, audit, logs"},
        {"name": "Approvals", "description": "Human-in-the-loop approvals"},
        {"name": "Webhooks", "description": "VIP webhook (HMAC)"},
    ],
)

# OpenAPI security schemes — muncul di Swagger UI "Authorize" button
app.openapi_schema = None  # force re-generate

_original_openapi = app.openapi


def _patched_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = _original_openapi()
    schema["components"] = schema.get("components", {})
    schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key dalam format `fr_xxxx...`. Dapatkan via POST /users.",
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "API Key",
            "description": "Bearer token: `Authorization: Bearer fr_xxxxx...`",
        },
    }
    # Global security — semua endpoint default pakai auth
    schema["security"] = [{"ApiKeyAuth": []}, {"BearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = _patched_openapi  # type: ignore[method-assign]

# P3.4 — CORS: explicit allowlist (never * with credentials)
_allowed_origins = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
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
app.include_router(marketplace_router)
app.include_router(system_router)
app.include_router(control_router)
app.include_router(webhooks_router)

from src.api.routes_billing import router as billing_router  # noqa: E402

app.include_router(billing_router)

if __name__ == "__main__":
    import uvicorn

    _host = os.getenv("API_HOST", "127.0.0.1")
    _port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run(app, host=_host, port=_port)
