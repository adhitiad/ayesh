from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import sessionmaker

from src.core.auth.approval import decide, list_pending
from src.core.auth.auth import require_authenticated, require_owner
from src.core.db.db_engine import get_engine
from src.core.db.models import PendingApproval

router = APIRouter()


@router.get("/approvals/pending")
def approvals_pending(request: Request):
    owner_user_id = require_authenticated(request)
    return list_pending(owner_user_id)


@router.post("/approvals/{aid}/approve")
def approval_approve(request: Request, aid: str):
    require_authenticated(request)
    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        row = db.query(PendingApproval).filter(PendingApproval.id == aid).first()
    if not row:
        raise HTTPException(status_code=404, detail="Approval tidak ditemukan/sudah diputus")
    require_owner(request, str(row.owner_user_id))
    if not decide(aid, True, str(row.owner_user_id)):
        raise HTTPException(status_code=404, detail="Approval tidak ditemukan/sudah diputus")
    return {"status": "approved", "id": aid}


@router.post("/approvals/{aid}/deny")
def approval_deny(request: Request, aid: str):
    require_authenticated(request)
    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        row = db.query(PendingApproval).filter(PendingApproval.id == aid).first()
    if not row:
        raise HTTPException(status_code=404, detail="Approval tidak ditemukan/sudah diputus")
    require_owner(request, str(row.owner_user_id))
    if not decide(aid, False, str(row.owner_user_id)):
        raise HTTPException(status_code=404, detail="Approval tidak ditemukan/sudah diputus")
    return {"status": "denied", "id": aid}
