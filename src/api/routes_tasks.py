from fastapi import APIRouter, HTTPException, Request

from src.api.models import TaskRequest
from src.core.auth.auth import require_authenticated
from src.core.scheduler.tasks import get_task, list_tasks, submit_task
from src.core.system.error_handling import generate_request_id

router = APIRouter()


@router.post("/tasks", status_code=202)
def submit_task_endpoint(req: TaskRequest, request: Request):
    owner_user_id = require_authenticated(request)
    request_id = generate_request_id()
    result = submit_task(req.message, req.session_id, owner_user_id, owner_user_id)
    result["request_id"] = request_id
    return result


@router.get("/tasks")
def list_tasks_endpoint(request: Request, offset: int = 0, limit: int = 20):
    owner_user_id = require_authenticated(request)
    request_id = generate_request_id()
    tasks = list_tasks(offset=offset, limit=min(limit, 100), owner_user_id=owner_user_id)
    return {"tasks": tasks, "request_id": request_id, "offset": offset, "limit": limit}


@router.get("/tasks/{task_id}")
def get_task_endpoint(request: Request, task_id: str):
    owner_user_id = require_authenticated(request)
    request_id = generate_request_id()
    task = get_task(task_id, owner_user_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    task["request_id"] = request_id
    return task
