from fastapi import APIRouter
from fastapi import Request, HTTPException
from src.core.auth import require_auth, require_owner
from src.core.approval import list_pending, decide
from src.core.db import connect

router = APIRouter()

@router.get("/approvals/pending")
def approvals_pending(request: Request):
    owner_user_id = require_auth(request)
    return list_pending(owner_user_id)

@router.post("/approvals/{aid}/approve")
def approval_approve(request: Request, aid: str):
    owner_user_id = require_auth(request)
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT owner_user_id FROM pending_approvals WHERE id = %s;", (aid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(
            status_code=404, detail="Approval tidak ditemukan/sudah diputus"
        )
    require_owner(request, row[0])
    if not decide(aid, True, row[0]):
        raise HTTPException(
            status_code=404, detail="Approval tidak ditemukan/sudah diputus"
        )
    return {"status": "approved", "id": aid}

@router.post("/approvals/{aid}/deny")
def approval_deny(request: Request, aid: str):
    owner_user_id = require_auth(request)
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT owner_user_id FROM pending_approvals WHERE id = %s;", (aid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(
            status_code=404, detail="Approval tidak ditemukan/sudah diputus"
        )
    require_owner(request, row[0])
    if not decide(aid, False, row[0]):
        raise HTTPException(
            status_code=404, detail="Approval tidak ditemukan/sudah diputus"
        )
    return {"status": "denied", "id": aid}
