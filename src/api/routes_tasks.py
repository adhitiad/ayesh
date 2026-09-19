from fastapi import APIRouter
from fastapi import Request, HTTPException
from src.api.models import TaskRequest, ChatRequest
from src.core.auth import require_auth
from src.core.tasks import submit_task, list_tasks, get_task

router = APIRouter()

@router.post("/tasks", status_code=202)
def submit_task_endpoint(req: TaskRequest, request: Request):
    owner_user_id = require_auth(request)
    return submit_task(req.message, req.session_id, owner_user_id, owner_user_id)

@router.get("/tasks")
def list_tasks_endpoint(request: Request, limit: int = 20):
    owner_user_id = require_auth(request)
    return list_tasks(limit=limit, owner_user_id=owner_user_id)

@router.get("/tasks/{task_id}")
def get_task_endpoint(request: Request, task_id: str):
    owner_user_id = require_auth(request)
    task = get_task(task_id, owner_user_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    return task
