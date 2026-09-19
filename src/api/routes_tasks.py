from fastapi import APIRouter, HTTPException, Request

from src.api.models import TaskRequest
from src.core.auth.auth import require_auth
from src.core.scheduler.tasks import get_task, list_tasks, submit_task

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
