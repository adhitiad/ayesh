from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.api.models import (
    SkillOverrideRequest,
    UserLLMConfigRequest,
    UserMcpOverrideRequest,
    UserRequest,
)
from src.config.rules import AGENT_RULES, SUBAGENTS
from src.core.auth.auth import (
    add_user_llm_config,
    bootstrap_owner,
    create_user,
    deactivate_user,
    delete_user_llm_config,
    is_mcp_enabled_for_user,
    is_skill_enabled_for_user,
    list_user_llm_configs,
    list_user_mcp_overrides,
    list_user_skill_overrides,
    list_users,
    require_admin,
    require_auth,
    require_owner_only,
    rotate_user_key,
    set_user_mcp_override,
    set_user_skill_override,
    update_user_llm_config_entry,
)
from src.core.system.error_handling import generate_request_id
from src.mcp_core.skills import list_skills, load_skill

router = APIRouter()


def _require_ownership(request: Request, uid: str) -> None:
    """Raise 403 jika user bukan owner/admin dan bukan owner data."""
    from fastapi import HTTPException

    from src.core.auth.auth_context import get_current_user, get_current_user_role

    viewer_uid = get_current_user()
    viewer_role = get_current_user_role()
    if viewer_uid != uid and viewer_role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Tidak punya akses ke data user lain")


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

    user = create_user(req.name, req.role or "user")
    user["warning"] = "Simpan api_key sekarang - tidak ditampilkan lagi."
    user["request_id"] = request_id
    return user


@router.post("/users/bootstrap")
def bootstrap_owner_endpoint(request: Request):
    request_id = generate_request_id()

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
def list_users_endpoint(request: Request, limit: int = 50):
    require_admin(request)
    request_id = generate_request_id()
    limit = min(limit, 100)
    users = list_users()
    return {"users": users[:limit], "request_id": request_id}


@router.post("/users/{uid}/rotate")
def rotate_user_key_endpoint(request: Request, uid: str):
    require_owner_only(request)
    request_id = generate_request_id()

    result = rotate_user_key(uid)
    if not result:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    result["warning"] = "Simpan api_key baru sekarang - key lama otomatis dinonaktifkan setelah masa tenggang (24 jam)."
    result["request_id"] = request_id
    return result


@router.delete("/users/{uid}")
def delete_user_endpoint(request: Request, uid: str):
    require_admin(request)
    request_id = generate_request_id()
    if not deactivate_user(uid):
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return {"status": "deactivated", "id": uid, "request_id": request_id}


# ── Per-user LLM configs ──────────────────────────────────────────────


@router.get("/users/{uid}/llm-configs")
def list_user_llm_configs_endpoint(request: Request, uid: str):
    require_auth(request)
    request_id = generate_request_id()

    from src.core.auth.auth_context import get_current_user, get_current_user_role

    viewer_uid = get_current_user()
    viewer_role = get_current_user_role()
    is_self = viewer_uid == uid
    is_privileged = viewer_role in ("owner", "admin")

    if not is_self and not is_privileged:
        raise HTTPException(status_code=403, detail="Tidak bisa melihat config user lain")

    configs = list_user_llm_configs(uid, viewer_uid=viewer_uid, viewer_role=viewer_role)
    return {"configs": configs, "request_id": request_id}


@router.post("/users/{uid}/llm-configs")
def add_user_llm_config_endpoint(request: Request, uid: str, req: UserLLMConfigRequest):
    require_auth(request)
    _require_ownership(request, uid)
    request_id = generate_request_id()
    result = add_user_llm_config(
        uid,
        provider=req.provider,
        model=req.model,
        api_key=req.api_key,
        temperature=req.temperature,
        is_default=req.is_default or False,
        is_public=req.is_public or False,
    )
    result["request_id"] = request_id
    return result


@router.put("/users/{uid}/llm-configs/{config_id}")
def update_user_llm_config_endpoint(request: Request, uid: str, config_id: str, req: UserLLMConfigRequest):
    require_auth(request)
    _require_ownership(request, uid)
    request_id = generate_request_id()
    result = update_user_llm_config_entry(
        uid,
        config_id,
        api_key=req.api_key,
        model=req.model,
        temperature=req.temperature,
        is_default=req.is_default,
        is_public=req.is_public,
    )
    if not result:
        raise HTTPException(status_code=404, detail="LLM config tidak ditemukan")
    result["request_id"] = request_id
    return result


@router.delete("/users/{uid}/llm-configs/{config_id}")
def delete_user_llm_config_endpoint(request: Request, uid: str, config_id: str):
    require_auth(request)
    _require_ownership(request, uid)
    request_id = generate_request_id()
    if not delete_user_llm_config(uid, config_id):
        raise HTTPException(status_code=404, detail="LLM config tidak ditemukan")
    return {"status": "deleted", "id": config_id, "request_id": request_id}


@router.put("/users/{uid}/llm-configs/{config_id}/fallback")
def set_fallback_chain_endpoint(request: Request, uid: str, config_id: str, req: UserLLMConfigRequest):
    """Set fallback chain untuk LLM config. fallback_config_ids: list of config IDs."""
    require_auth(request)
    _require_ownership(request, uid)
    request_id = generate_request_id()
    import json

    result = update_user_llm_config_entry(uid, config_id, fallback_config_ids=json.dumps(req.fallback_config_ids or []))
    if result is None:
        raise HTTPException(status_code=404, detail="LLM config tidak ditemukan")
    result["request_id"] = request_id
    return result


# ── Per-user skill overrides ──────────────────────────────────────────


@router.get("/users/{uid}/skill-overrides")
def list_skill_overrides_endpoint(request: Request, uid: str):
    require_auth(request)
    request_id = generate_request_id()
    overrides = list_user_skill_overrides(uid)
    return {"overrides": overrides, "request_id": request_id}


@router.put("/users/{uid}/skill-overrides")
def set_skill_override_endpoint(request: Request, uid: str, req: SkillOverrideRequest):
    require_auth(request)
    _require_ownership(request, uid)
    request_id = generate_request_id()
    result = set_user_skill_override(uid, req.skill_name, req.enabled)
    result["request_id"] = request_id
    return result


@router.get("/users/{uid}/skill-overrides/{skill_name}")
def check_skill_enabled_endpoint(request: Request, uid: str, skill_name: str):
    require_auth(request)
    request_id = generate_request_id()
    enabled = is_skill_enabled_for_user(uid, skill_name)
    return {"skill_name": skill_name, "enabled": enabled, "request_id": request_id}


# ── Per-user MCP overrides ────────────────────────────────────────────


@router.get("/users/{uid}/mcp-overrides")
def list_mcp_overrides_endpoint(request: Request, uid: str):
    require_auth(request)
    request_id = generate_request_id()
    overrides = list_user_mcp_overrides(uid)
    return {"overrides": overrides, "request_id": request_id}


@router.put("/users/{uid}/mcp-overrides")
def set_mcp_override_endpoint(request: Request, uid: str, req: UserMcpOverrideRequest):
    require_auth(request)
    _require_ownership(request, uid)
    request_id = generate_request_id()
    result = set_user_mcp_override(uid, req.mcp_name, req.enabled)
    result["request_id"] = request_id
    return result


@router.get("/users/{uid}/mcp-overrides/{mcp_name}")
def check_mcp_enabled_endpoint(request: Request, uid: str, mcp_name: str):
    require_auth(request)
    request_id = generate_request_id()
    enabled = is_mcp_enabled_for_user(uid, mcp_name)
    return {"mcp_name": mcp_name, "enabled": enabled, "request_id": request_id}


# ── Bulk overrides ────────────────────────────────────────────────────


class BulkSkillOverrideRequest(BaseModel):
    overrides: list[SkillOverrideRequest]


class BulkMcpOverrideRequest(BaseModel):
    overrides: list[UserMcpOverrideRequest]


@router.patch("/users/{uid}/skill-overrides")
def bulk_skill_overrides_endpoint(request: Request, uid: str, req: BulkSkillOverrideRequest):
    """Bulk update skill overrides — array of {skill_name, enabled}."""
    require_auth(request)
    _require_ownership(request, uid)
    request_id = generate_request_id()
    results = []
    for o in req.overrides:
        results.append(set_user_skill_override(uid, o.skill_name, o.enabled))
    return {"results": results, "count": len(results), "request_id": request_id}


@router.patch("/users/{uid}/mcp-overrides")
def bulk_mcp_overrides_endpoint(request: Request, uid: str, req: BulkMcpOverrideRequest):
    """Bulk update MCP overrides — array of {mcp_name, enabled}."""
    require_auth(request)
    _require_ownership(request, uid)
    request_id = generate_request_id()
    results = []
    for o in req.overrides:
        results.append(set_user_mcp_override(uid, o.mcp_name, o.enabled))
    return {"results": results, "count": len(results), "request_id": request_id}
