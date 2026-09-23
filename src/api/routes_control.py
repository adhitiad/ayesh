"""Endpoint control-plane tambahan: keyword CRUD, plans, template delete, session delete.

Dipisah dari routes_system.py agar kedua file tetap dalam batas 410 baris.
Semua endpoint di sini fail-closed: require_admin / require_authenticated
+ require_owner, choke-point sanitize_keyword_tools, audit hash-chain.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from src.config.routing_keywords_pg import (
    add_keyword_with_tools,
    invalidate_routing_cache,
    remove_keyword,
    sanitize_keyword_tools,
)
from src.core.auth.audit import append_audit
from src.core.auth.auth import require_admin, require_authenticated, require_owner
from src.core.db.db_engine import get_engine
from src.core.db.models import Plan, PlanStep, Session, SessionMemory
from src.core.llm import templates as prompt_templates
from src.core.system.error_handling import generate_request_id

logger = logging.getLogger(__name__)

router = APIRouter()

_SessionLocal = sessionmaker(bind=get_engine())


@router.post("/keywords")
async def create_keyword(request: Request):
    """Tambah/update keyword routing (admin). allowed_tools di-choke-point."""
    actor = require_admin(request)
    request_id = generate_request_id()
    try:
        body = await request.json()
    except Exception as _e:
        raise HTTPException(status_code=400, detail="body harus JSON") from _e
    agent = str(body.get("agent") or "").strip()
    keyword = str(body.get("keyword") or "").strip().lower()
    allowed_tools = body.get("allowed_tools") or []
    if not agent or not keyword:
        raise HTTPException(status_code=400, detail="agent dan keyword wajib diisi")
    if len(keyword) > 100:
        raise HTTPException(status_code=400, detail="keyword maksimal 100 karakter")
    if not isinstance(allowed_tools, list):
        raise HTTPException(status_code=400, detail="allowed_tools harus berupa list")
    clean = sanitize_keyword_tools(agent, allowed_tools)
    if clean is None:
        raise HTTPException(status_code=400, detail="agent tidak valid (fail-closed)")
    if not add_keyword_with_tools(agent, keyword, clean):
        raise HTTPException(status_code=400, detail="gagal menyimpan keyword (cek DATABASE_URL)")
    invalidate_routing_cache()
    try:
        append_audit("keyword_add", actor=actor, details={"agent": agent, "keyword": keyword, "tools": clean})
    except Exception as _e:
        logger.error("audit keyword_add gagal, rollback: %s", _e)
        remove_keyword(agent, keyword)
        invalidate_routing_cache()
        raise HTTPException(status_code=500, detail="audit keyword_add gagal; perubahan di-rollback") from _e
    return {"ok": True, "agent": agent, "keyword": keyword, "allowed_tools": clean, "request_id": request_id}


@router.delete("/keywords")
def delete_keyword(request: Request, agent: str, keyword: str):
    """Hapus keyword routing (admin). Query params agar keyword bebas spasi."""
    actor = require_admin(request)
    request_id = generate_request_id()
    agent = (agent or "").strip()
    keyword = (keyword or "").strip().lower()
    if not agent or not keyword:
        raise HTTPException(status_code=400, detail="agent dan keyword wajib diisi")
    if sanitize_keyword_tools(agent, []) is None:
        raise HTTPException(status_code=400, detail="agent tidak valid (fail-closed)")
    if not remove_keyword(agent, keyword):
        raise HTTPException(status_code=404, detail="keyword tidak ditemukan")
    invalidate_routing_cache()
    try:
        append_audit("keyword_delete", actor=actor, details={"agent": agent, "keyword": keyword})
    except Exception as _e:
        logger.warning("audit keyword_delete gagal: %s", _e)
    return {"ok": True, "agent": agent, "keyword": keyword, "request_id": request_id}


@router.get("/plans")
def list_plans(request: Request, status: str | None = None, limit: int = 20):
    """Daftar rencana milik user (owner-scoped, pola /sessions)."""
    owner_user_id = require_authenticated(request)
    request_id = generate_request_id()
    limit = max(1, min(50, limit))
    stmt = select(Plan).where(Plan.owner_user_id == owner_user_id)
    if status and status.strip().lower() not in ("", "semua"):
        stmt = stmt.where(Plan.status == status.strip().lower())
    with _SessionLocal() as db:
        rows = db.execute(stmt.order_by(Plan.updated_at.desc()).limit(limit)).scalars().all()
    return {
        "request_id": request_id,
        "plans": [
            {
                "id": p.id,
                "judul": p.judul,
                "tujuan": p.tujuan,
                "status": p.status,
                "langkah_selesai": p.langkah_selesai,
                "total_langkah": p.total_langkah,
                "created_at": str(p.created_at),
                "updated_at": str(p.updated_at),
            }
            for p in rows
        ],
        "count": len(rows),
        "limit": limit,
    }


@router.get("/plans/{plan_id}")
def get_plan(request: Request, plan_id: str):
    """Detail rencana + langkah (pola /sessions/{id}: 404 lalu require_owner)."""
    require_authenticated(request)
    request_id = generate_request_id()
    with _SessionLocal() as db:
        plan = db.execute(select(Plan).where(Plan.id == plan_id.strip())).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Rencana tidak ditemukan")
        require_owner(request, str(plan.owner_user_id))
        steps = (
            db.execute(select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.urutan)).scalars().all()
        )
    return {
        "request_id": request_id,
        "id": plan.id,
        "owner_user_id": plan.owner_user_id,
        "judul": plan.judul,
        "tujuan": plan.tujuan,
        "status": plan.status,
        "langkah_selesai": plan.langkah_selesai,
        "total_langkah": plan.total_langkah,
        "created_at": str(plan.created_at),
        "updated_at": str(plan.updated_at),
        "steps": [
            {
                "urutan": s.urutan,
                "deskripsi": s.deskripsi,
                "status": s.status,
                "hasil": s.hasil,
            }
            for s in steps
        ],
    }


@router.patch("/plans/{plan_id}")
async def update_plan_status(request: Request, plan_id: str):
    """Ubah status rencana (owner-scoped; mirror tool tandai_selesai/batal_plan)."""
    require_authenticated(request)
    request_id = generate_request_id()
    try:
        body = await request.json()
    except Exception as _e:
        raise HTTPException(status_code=400, detail="body harus JSON") from _e
    status = str(body.get("status") or "").strip().lower()
    if status not in ("aktif", "selesai", "batal"):
        raise HTTPException(status_code=400, detail="status harus aktif/selesai/batal")
    with _SessionLocal() as db:
        plan = db.execute(select(Plan).where(Plan.id == plan_id.strip())).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Rencana tidak ditemukan")
        require_owner(request, str(plan.owner_user_id))
        if plan.status == "selesai" and status == "batal":
            raise HTTPException(status_code=409, detail="rencana sudah selesai, tidak bisa dibatalkan")
        plan.status = status
        plan.updated_at = datetime.now(UTC)
        db.commit()
        pid = plan.id
    return {"ok": True, "id": pid, "status": status, "request_id": request_id}


@router.delete("/sessions/{session_id}")
def delete_session(request: Request, session_id: str):
    """Hapus session beserta memonya (owner-scoped, pola clear_memory)."""
    require_authenticated(request)
    request_id = generate_request_id()
    sid = session_id.strip()
    with _SessionLocal() as db:
        sess = db.query(Session).filter(Session.id == sid).first()
        if not sess:
            raise HTTPException(status_code=404, detail="Session tidak ditemukan")
        require_owner(request, str(sess.owner_user_id))
        db.execute(delete(SessionMemory).where(SessionMemory.session_id == sid))
        db.delete(sess)
        db.commit()
    logger.info("session dihapus via API: %s", sid)
    return {"ok": True, "deleted": sid, "request_id": request_id}


@router.delete("/templates/{name}")
def delete_prompt_template(request: Request, name: str):
    """Hapus template kustom (admin). Template bawaan ditolak 400."""
    actor = require_admin(request)
    request_id = generate_request_id()
    try:
        prompt_templates.delete_template(name)
    except ValueError as _e:
        raise HTTPException(status_code=400, detail=str(_e)) from _e
    except KeyError as _e:
        raise HTTPException(status_code=404, detail=str(_e)) from _e
    try:
        append_audit("template_delete", actor=actor, details={"name": (name or "").strip()})
    except Exception as _e:
        logger.warning("audit template_delete gagal: %s", _e)
    return {"ok": True, "name": (name or "").strip(), "request_id": request_id}
