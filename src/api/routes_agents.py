from fastapi import APIRouter
from fastapi import Request, HTTPException
from src.api.models import UserRequest, JobRequest, ChatRequest
from src.core.auth import require_auth, require_admin, require_owner_or_admin, require_owner_only
from src.core.auth import create_user, list_users, deactivate_user, bootstrap_owner
from src.config.rules import SUBAGENTS, AGENT_RULES
from src.mcp_core.skills import list_skills, load_skill
from src.core.rate_limit import check_rate_limit

router = APIRouter()

@router.get("/agents")
def list_agents(request: Request):
    require_auth(request)
    return [
        {
            "name": name,
            "role": AGENT_RULES.get(name, {}).get("role", ""),
            "description": cfg.get("description", ""),
            "when_to_use": cfg.get("when_to_use", ""),
            "tools": cfg.get("tools", []),
        }
        for name, cfg in SUBAGENTS.items()
    ]

@router.get("/skills")
def list_skills_endpoint(request: Request):
    require_auth(request)
    return list_skills()

@router.get("/skills/{skill_name}")
def get_skill(request: Request, skill_name: str):
    require_auth(request)
    skill = load_skill(skill_name)
    if not skill:
        raise HTTPException(
            status_code=404, detail=f"Skill '{skill_name}' tidak ditemukan"
        )
    return skill

@router.post("/users")
async def create_user_endpoint(request: Request, req: UserRequest):
    require_owner_only(request)

    client_ip = request.client.host if request.client else "unknown"
    allowed, info = check_rate_limit("users", client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit: max 5 user creations per minute.",
        )

    user = create_user(req.name, req.role)
    user["warning"] = "Simpan api_key sekarang - tidak ditampilkan lagi."
    return user

@router.post("/users/bootstrap")
def bootstrap_owner_endpoint(request: Request):
    from src.core.auth import bootstrap_owner, _conn, _ensure_table

    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'owner' AND active = TRUE;")
    count = cur.fetchone()[0]
    conn.close()
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
    user["warning"] = (
        "SIMPAN API KEY SEKARANG - tidak ditampilkan lagi. Ini satu-satunya kali."
    )
    return user

@router.get("/users")
def list_users_endpoint(request: Request):
    require_admin(request)
    return list_users()

@router.delete("/users/{uid}")
def delete_user_endpoint(request: Request, uid: str):
    require_admin(request)
    if not deactivate_user(uid):
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return {"status": "deactivated", "id": uid}
