from fastapi import APIRouter, HTTPException, Request

from main import route_request
from src.api.models import JobRequest
from src.core.auth.auth import require_auth
from src.core.db.db import connect
from src.core.scheduler.scheduler import create_job, delete_job, list_jobs, set_enabled
from src.core.system.error_handling import generate_request_id, log_internal_error

router = APIRouter()


@router.post("/jobs")
def create_job_endpoint(request: Request, req: JobRequest):
    owner_user_id = require_auth(request)
    try:
        return create_job(
            req.name,
            req.prompt,
            req.interval_detik,
            req.daily_at,
            user_id=owner_user_id,
            owner_user_id=owner_user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/jobs")
def list_jobs_endpoint(request: Request):
    owner_user_id = require_auth(request)
    return list_jobs(user_id=owner_user_id)


@router.delete("/jobs/{job_id}")
def delete_job_endpoint(request: Request, job_id: str):
    owner_user_id = require_auth(request)
    if not delete_job(job_id, owner_user_id):
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return {"status": "deleted", "id": job_id}


@router.patch("/jobs/{job_id}")
def toggle_job_endpoint(request: Request, job_id: str, enabled: bool = True):
    owner_user_id = require_auth(request)
    if not set_enabled(job_id, enabled, owner_user_id):
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    return {"status": "ok", "id": job_id, "enabled": enabled}


@router.post("/jobs/{job_id}/run")
def run_job_once(request: Request, job_id: str):
    owner_user_id = require_auth(request)
    jobs = [j for j in list_jobs(owner_user_id) if j["id"] == job_id]
    if not jobs:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    # Ambil prompt penuh dari DB lalu eksekusi sekali
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT prompt, session_id FROM scheduled_jobs WHERE id = %s AND owner_user_id = %s;",
        (job_id, owner_user_id),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    try:
        result = route_request(row[0], row[1])
        return {"status": "ok", "id": job_id, "agent": result.get("agent_type")}
    except Exception as e:
        request_id = generate_request_id()
        log_internal_error(request_id, e, context=f"job_run:{job_id}")
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "request_id": request_id},
        ) from e
