from fastapi import APIRouter, HTTPException, Request

from src.api.models import UserRequest
from src.config.rules import AGENT_RULES, SUBAGENTS
from src.core.auth.auth import (
    bootstrap_owner,
    create_user,
    deactivate_user,
    list_users,
    require_admin,
    require_auth,
    require_owner_only,
)
from src.core.system.error_handling import generate_request_id
from src.core.system.rate_limit import check_rate_limit
from src.mcp_core.skills import list_skills, load_skill

router = APIRouter()


@router.get("/agents")
def list_agents(request: Request):
    require_auth(request)
    request_id = generate_request_id()
    agents = [
        {
            "name": name,
            "role": AGENT_RULES.get(name, {}).get("role", ""),
            "description": cfg.get("description", ""),
            "when_to_use": cfg.get("when_to_use", ""),
            "tools": cfg.get("tools", []),
        }
        for name, cfg in SUBAGENTS.items()
    ]
    return {"agents": agents, "request_id": request_id}


@router.get("/skills")
def list_skills_endpoint(request: Request):
    require_auth(request)
    request_id = generate_request_id()
    skills = list_skills()
    return {"skills": skills, "request_id": request_id}


@router.get("/skills/{skill_name}")
def get_skill(request: Request, skill_name: str):
    require_auth(request)
    request_id = generate_request_id()
    skill = load_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' tidak ditemukan")
    skill["request_id"] = request_id
    return skill


@router.post("/users")
async def create_user_endpoint(request: Request, req: UserRequest):
    require_owner_only(request)
    request_id = generate_request_id()

    client_ip = request.client.host if request.client else "unknown"
    allowed, _info = check_rate_limit("users", client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit: max 5 user creations per minute.",
        )

    user = create_user(req.name, req.role)
    user["warning"] = "Simpan api_key sekarang - tidak ditampilkan lagi."
    user["request_id"] = request_id
    return user


@router.post("/users/bootstrap")
def bootstrap_owner_endpoint(request: Request):
    request_id = generate_request_id()

    client_ip = request.client.host if request.client else "unknown"
    allowed, _info = check_rate_limit("bootstrap", client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit: max 3 bootstrap attempts per minute.",
        )

    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine
    from src.core.db.models import Base, User

    Base.metadata.create_all(get_engine(), tables=[User.__table__])
    SessionLocal = sessionmaker(bind=get_engine())
    with SessionLocal() as db:
        count = db.query(User).filter(User.role == "owner", User.active == True).count()  # noqa: E712
    if count > 0:
        raise HTTPException(
            status_code=403,
            detail="Owner sudah ada. Gunakan POST /users dengan owner key untuk membuat user baru.",
        )

    user = bootstrap_owner()
    if not user:
        raise HTTPException(
            status_code=409,
            detail="Owner sudah ada (race condition).",
        )
    user["warning"] = "SIMPAN API KEY SEKARANG - tidak ditampilkan lagi. Ini satu-satunya kali."
    user["request_id"] = request_id
    return user


@router.get("/users")
def list_users_endpoint(request: Request):
    require_admin(request)
    request_id = generate_request_id()
    users = list_users()
    return {"users": users, "request_id": request_id}


@router.delete("/users/{uid}")
def delete_user_endpoint(request: Request, uid: str):
    require_admin(request)
    request_id = generate_request_id()
    if not deactivate_user(uid):
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return {"status": "deactivated", "id": uid, "request_id": request_id}
