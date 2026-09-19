from fastapi import APIRouter, HTTPException, Request

from main import route_request
from src.api.models import JobRequest
from src.core.auth.auth import require_auth
from src.core.scheduler.scheduler import create_job, delete_job, list_jobs, set_enabled
from src.core.system.error_handling import generate_request_id, log_internal_error

router = APIRouter()


@router.post("/jobs")
def create_job_endpoint(request: Request, req: JobRequest):
    owner_user_id = require_auth(request)
    request_id = generate_request_id()
    try:
        result = create_job(
            req.name,
            req.prompt,
            req.interval_detik,
            req.daily_at,
            user_id=owner_user_id,
            owner_user_id=owner_user_id,
        )
        result["request_id"] = request_id
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/jobs")
def list_jobs_endpoint(request: Request, offset: int = 0, limit: int = 50):
    owner_user_id = require_auth(request)
    request_id = generate_request_id()
    jobs = list_jobs(user_id=owner_user_id, offset=offset, limit=min(limit, 100))
    return {"jobs": jobs, "request_id": request_id, "offset": offset, "limit": limit}


@router.delete("/jobs/{job_id}")
def delete_job_endpoint(request: Request, job_id: str):
    owner_user_id = require_auth(request)
    request_id = generate_request_id()
    if not delete_job(job_id, owner_user_id):
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return {"status": "deleted", "id": job_id, "request_id": request_id}


@router.patch("/jobs/{job_id}")
def toggle_job_endpoint(request: Request, job_id: str, enabled: bool = True):
    owner_user_id = require_auth(request)
    request_id = generate_request_id()
    if not set_enabled(job_id, enabled, owner_user_id):
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return {"status": "ok", "id": job_id, "enabled": enabled, "request_id": request_id}


@router.post("/jobs/{job_id}/run")
def run_job_once(request: Request, job_id: str):
    owner_user_id = require_auth(request)
    jobs = [j for j in list_jobs(owner_user_id) if j["id"] == job_id]
    if not jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    # Ambil prompt penuh dari DB lalu eksekusi sekali
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine
    from src.core.db.models import ScheduledJob

    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        row = (
            db.query(ScheduledJob)
            .filter(ScheduledJob.id == job_id, ScheduledJob.owner_user_id == owner_user_id)
            .first()
        )
    if not row:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    try:
        result = route_request(row.prompt, row.session_id)
        return {"status": "ok", "id": job_id, "agent": result.get("agent_type")}
    except Exception as e:
        request_id = generate_request_id()
        log_internal_error(request_id, e, context=f"job_run:{job_id}")
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "request_id": request_id},
        ) from e
