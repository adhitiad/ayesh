from src.api.routes_chat import router as chat_router
from src.api.routes_feedback import router as feedback_router
from src.api.routes_agents import router as agents_router
from src.api.routes_jobs import router as jobs_router
from src.api.routes_tasks import router as tasks_router
from src.api.routes_approvals import router as approvals_router
from src.api.routes_system import router as system_router

chat = chat_router
feedback = feedback_router
agents = agents_router
jobs = jobs_router
tasks = tasks_router
approvals = approvals_router
system = system_router

__all__ = ["chat", "feedback", "agents", "jobs", "tasks", "approvals", "system"]
