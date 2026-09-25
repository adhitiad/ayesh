"""Billing history: GET /billing/history, GET /billing/history/{ref}, GET /billing/status/{ref}.

History disimpan di vip_upgrades (status pending|success|failed|expired).
Dashboard di ayesh-core (GET /billing/history) — ayesh-payment hanya caller HMAC ke /webhooks/vip-upgrade.
"""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import sessionmaker

from src.core.auth.auth import require_authenticated
from src.core.auth.auth_context import _utcnow, get_current_user, get_current_user_role
from src.core.auth.auth_keys import _ensure_vip_tables
from src.core.db.db_engine import get_engine
from src.core.db.models import User, VipUpgrade
from src.core.system.error_handling import generate_request_id

router = APIRouter(prefix="/billing")

_SessionLocal = sessionmaker(bind=get_engine())


def _vip_state(u: User | None) -> tuple[bool, str | None]:
    """→ (vip_active, vip_expires_at)."""
    if not u:
        return False, None
    exp = getattr(u, "vip_expires_at", None)
    expires = str(exp) if exp else None
    if u.role != "vip":
        return False, expires
    if not exp:
        return True, None
    try:
        return exp > _utcnow(), expires
    except Exception:
        return False, expires


@router.get("/history")
def billing_history(
    request: Request, uid: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0
):
    require_authenticated(request)
    request_id = generate_request_id()
    role = get_current_user_role()
    me = get_current_user()
    target = (uid or me).strip()
    if target != me and role != "owner":
        raise HTTPException(status_code=403, detail="Hanya owner bisa lihat billing user lain")
    if status and status not in ("pending", "success", "failed", "expired"):
        raise HTTPException(status_code=400, detail="status harus pending|success|failed|expired")
    limit = max(1, min(100, limit))
    offset = max(0, offset)
    _ensure_vip_tables()
    with _SessionLocal() as db:
        q = db.query(VipUpgrade).filter(VipUpgrade.user_id == target)
        if status:
            q = q.filter(VipUpgrade.status == status)
        rows = q.order_by(VipUpgrade.created_at.desc()).offset(offset).limit(limit).all()
        total = q.count()
    items = [
        {
            "id": r.id,
            "user_id": r.user_id,
            "external_ref": r.external_ref,
            "amount_cents": r.amount_cents,
            "currency": r.currency,
            "status": r.status,
            "provider": r.provider,
            "created_at": str(r.created_at) if r.created_at else None,
            "paid_at": str(r.paid_at) if getattr(r, "paid_at", None) else None,
            "applied_at": str(r.applied_at) if getattr(r, "applied_at", None) else None,
            "updated_at": str(r.updated_at) if getattr(r, "updated_at", None) else None,
        }
        for r in rows
    ]
    return {
        "request_id": request_id,
        "user_id": target,
        "items": items,
        "count": len(items),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/history/{external_ref}")
def billing_detail(request: Request, external_ref: str):
    require_authenticated(request)
    request_id = generate_request_id()
    me = get_current_user()
    role = get_current_user_role()
    _ensure_vip_tables()
    with _SessionLocal() as db:
        row = db.query(VipUpgrade).filter(VipUpgrade.external_ref == external_ref.strip()).first()
        if not row:
            raise HTTPException(status_code=404, detail="Billing tidak ditemukan")
        if row.user_id != me and role != "owner":
            raise HTTPException(status_code=403, detail="Hanya owner atau pemilik billing")
        u = db.query(User).filter(User.id == row.user_id).first()
        vip_active, vip_expires_at = _vip_state(u)
    return {
        "request_id": request_id,
        "id": row.id,
        "user_id": row.user_id,
        "external_ref": row.external_ref,
        "amount_cents": row.amount_cents,
        "currency": row.currency,
        "status": row.status,
        "provider": row.provider,
        "raw_payload": row.raw_payload if role == "owner" else None,
        "created_at": str(row.created_at) if row.created_at else None,
        "paid_at": str(row.paid_at) if getattr(row, "paid_at", None) else None,
        "updated_at": str(row.updated_at) if getattr(row, "updated_at", None) else None,
        "vip_active": vip_active,
        "vip_expires_at": vip_expires_at,
    }


@router.get("/status/{external_ref}")
def billing_status(request: Request, external_ref: str):
    require_authenticated(request)
    request_id = generate_request_id()
    me = get_current_user()
    role = get_current_user_role()
    _ensure_vip_tables()
    with _SessionLocal() as db:
        row = db.query(VipUpgrade).filter(VipUpgrade.external_ref == external_ref.strip()).first()
        if not row:
            raise HTTPException(status_code=404, detail="Billing tidak ditemukan")
        if row.user_id != me and role != "owner":
            raise HTTPException(status_code=403, detail="Hanya owner atau pemilik")
        u = db.query(User).filter(User.id == row.user_id).first()
        vip_active, vip_expires_at = _vip_state(u)
    return {
        "request_id": request_id,
        "external_ref": row.external_ref,
        "status": row.status,
        "vip_active": vip_active,
        "vip_expires_at": vip_expires_at,
    }
