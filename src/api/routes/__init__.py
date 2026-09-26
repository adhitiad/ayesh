from src.api.routes_agents import router as agents_router
from src.api.routes_approvals import router as approvals_router
from src.api.routes_auth import router as auth_router
from src.api.routes_billing import router as billing_router
from src.api.routes_chat import router as chat_router
from src.api.routes_control import router as control_router
from src.api.routes_feedback import router as feedback_router
from src.api.routes_jobs import router as jobs_router
from src.api.routes_marketplace import router as marketplace_router
from src.api.routes_system import router as system_router
from src.api.routes_tasks import router as tasks_router
from src.api.routes_webhooks import router as webhooks_router

chat = chat_router
feedback = feedback_router
agents = agents_router
jobs = jobs_router
tasks = tasks_router
approvals = approvals_router
system = system_router
auth = auth_router
billing = billing_router
control = control_router
marketplace = marketplace_router
webhooks = webhooks_router

__all__ = [
    "agents",
    "approvals",
    "auth",
    "billing",
    "chat",
    "control",
    "feedback",
    "jobs",
    "marketplace",
    "system",
    "tasks",
    "webhooks",
]
