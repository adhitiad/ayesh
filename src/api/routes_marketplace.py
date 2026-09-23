from fastapi import APIRouter, HTTPException, Request

from src.core.auth.auth import require_admin, require_authenticated
from src.plugins import marketplace as mp

router = APIRouter()


def _error(e: mp.MarketplaceError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message})


@router.get("/marketplace")
def marketplace_list(request: Request):
    """Daftar tool registry + status installed (butuh API key aktif)."""
    require_authenticated(request)
    return {"tools": mp.list_marketplace()}


@router.post("/marketplace/{name}/install")
def marketplace_install(name: str, request: Request):
    """Install tool dari registry (admin). Fail-closed: hash/path/validasi wajib lolos."""
    actor = require_admin(request) or ""
    try:
        return mp.install_tool(name, actor=actor)
    except mp.MarketplaceError as e:
        raise _error(e) from e


@router.delete("/marketplace/{name}")
def marketplace_uninstall(name: str, request: Request):
    """Hapus tool terpasang + cabut grant capabilities (admin)."""
    actor = require_admin(request) or ""
    try:
        return mp.uninstall_tool(name, actor=actor)
    except mp.MarketplaceError as e:
        raise _error(e) from e
