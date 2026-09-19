"""Human-in-the-loop approval: tool berbahaya jeda minta persetujuan.

Aktif hanya bila env REQUIRE_APPROVAL=1 (default mati agar eval/tes tak macet).
Setiap tool memerlukan explicit approval. Tidak ada auto-approve berbasis prefix.
Tool menunggu max APPROVAL_TIMEOUT_S (default 600); deny/timeout → tool
mengembalikan pesan error (agent tetap hidup menjelaskan ke user).

Gate (should_gate): jalankan_python selalu; panggil_mcp selalu;
tulis_kode hanya bila overwrite=True.
"""

import json as _json
import os
import time
import uuid
from contextvars import ContextVar

current_session: ContextVar[str] = ContextVar("approval_session", default="")
current_owner_user_id: ContextVar[str] = ContextVar("owner_user_id", default="")
current_agent_type: ContextVar[str] = ContextVar("agent_type", default="")

# P1.3 — MCP Policy: per-agent server → tool allowlist.
# Unknown server/tool → DENY. "filesystem" always blocked.
MCP_POLICY: dict[str, dict[str, set[str]]] = {
    "coder_agent": {
        "tavily": {"tavily_search"},
        "exa": {"exa_search"},
        "github": {"get_file", "list_files", "search_code"},
        "sequential-thinking": {"sequentialthinking"},
        "context7": {"resolve-library-id", "query-docs"},
    },
    "admin_agent": {
        "tavily": {"tavily_search"},
        "exa": {"exa_search"},
        "firecrawl": {"firecrawl_search", "firecrawl_scrape"},
        "sequential-thinking": {"sequentialthinking"},
    },
    "casual_agent": {},  # No MCP access by default
}

# Dangerous MCP operations that always require approval regardless of policy
MCP_DANGEROUS_TOOLS: set[str] = {
    "write_file",
    "create_file",
    "delete_file",
    "move_file",
    "execute_command",
    "run_command",
    "shell",
}


def set_current_agent_type(agent_type: str) -> None:
    current_agent_type.set(agent_type or "")


def get_current_agent_type() -> str:
    return current_agent_type.get()


def check_mcp_policy(server: str, tool: str) -> tuple[bool, str]:
    """Check if server+tool is allowed by MCP_POLICY for current agent.

    Returns (allowed, error_message). Fail-closed: unknown = deny.
    """
    agent = get_current_agent_type()
    if not agent:
        return False, "Error: agent context tidak tersedia; MCP call ditolak."

    # Hard block filesystem always
    if server == "filesystem":
        return False, "Error: Server 'filesystem' diblokir permanen."

    agent_policy = MCP_POLICY.get(agent)
    if agent_policy is None:
        return False, f"Error: agent '{agent}' tidak memiliki MCP policy."

    server_tools = agent_policy.get(server)
    if server_tools is None:
        return False, f"Error: server '{server}' tidak diizinkan untuk agent '{agent}'."

    if tool not in server_tools:
        return (
            False,
            f"Error: tool '{tool}' tidak diizinkan di server '{server}' untuk agent '{agent}'.",
        )

    # Dangerous tools always need approval even if in policy
    if tool in MCP_DANGEROUS_TOOLS:
        return False, f"Approval diperlukan untuk tool berbahaya '{tool}'."

    return True, ""


def set_current_session(session_id: str) -> None:
    current_session.set(session_id or "")


def set_current_owner_user_id(owner_user_id: str) -> None:
    current_owner_user_id.set(owner_user_id or "")


def approval_required() -> bool:
    return os.getenv("REQUIRE_APPROVAL", "0") == "1"


def approval_timeout() -> int:
    try:
        return max(5, int(os.getenv("APPROVAL_TIMEOUT_S", "600")))
    except ValueError:
        return 600


def should_gate(tool_name: str, args: dict) -> bool:
    """Pure: apakah pemanggilan ini perlu approval? (tanpa DB, testable)."""
    args = args or {}
    if tool_name == "jalankan_python":
        return True
    if tool_name == "panggil_mcp":
        return True
    return bool(tool_name == "tulis_kode" and args.get("overwrite") is True)


def _ensure_table(cur=None):
    """Ensure pending_approvals table exists. Accepts cursor (no-op) for backward compat."""
    from src.core.db.db_engine import get_engine
    from src.core.db.models import Base, PendingApproval

    Base.metadata.create_all(get_engine(), tables=[PendingApproval.__table__])


def _SessionLocal():
    from sqlalchemy.orm import sessionmaker

    from src.core.db.db_engine import get_engine

    return sessionmaker(bind=get_engine())


def request_approval(
    tool_name: str,
    args: dict,
    timeout_s: int | None = None,
    user_id: str = "default",
    owner_user_id: str | None = None,
) -> tuple[bool, str]:
    """Minta approval, blokir hingga diputus/timeout. Return (approved, approval_id)."""
    if owner_user_id is None:
        owner_user_id = user_id
    timeout_s = timeout_s or approval_timeout()
    aid = str(uuid.uuid4())

    _ensure_table()
    SessionLocal = _SessionLocal()
    with SessionLocal() as db:
        from src.core.db.models import PendingApproval

        pa = PendingApproval(
            id=aid,
            tool=tool_name,
            args=_json.dumps(args),
            session_id=current_session.get(),
            owner_user_id=owner_user_id,
            user_id=user_id,
            status="pending",
        )
        db.add(pa)
        db.commit()

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(5)
        with SessionLocal() as db:
            from src.core.db.models import PendingApproval

            pa = db.query(PendingApproval).filter(PendingApproval.id == aid).first()
            if pa and pa.status == "approved":
                return True, aid
            if pa and pa.status == "denied":
                return False, aid

    with SessionLocal() as db:
        from src.core.db.models import PendingApproval

        pa = db.query(PendingApproval).filter(PendingApproval.id == aid, PendingApproval.status == "pending").first()
        if pa:
            pa.status = "expired"
            pa.decided_at = db.execute(__import__("sqlalchemy").func.now()).scalar()
            db.commit()
    return False, aid


def ensure_approved(tool_name: str, args: dict, owner_user_id: str | None = None) -> tuple[bool, str]:
    """Gate utama dipanggil dari tool. Return (boleh_lanjut, pesan)."""
    if not approval_required():
        return True, ""
    if not should_gate(tool_name, args):
        return True, ""
    ok, aid = request_approval(tool_name, args, owner_user_id=owner_user_id)
    if ok:
        return True, ""
    return False, (f"Aksi {tool_name} DITOLAK/timeout (approval {aid}). Jelaskan ke user dan tawarkan alternatif aman.")


def list_pending(owner_user_id: str = "default") -> list:
    _ensure_table()
    SessionLocal = _SessionLocal()
    with SessionLocal() as db:
        from src.core.db.models import PendingApproval

        rows = (
            db.query(PendingApproval)
            .filter(PendingApproval.status == "pending", PendingApproval.owner_user_id == owner_user_id)
            .order_by(PendingApproval.id)
            .all()
        )
        return [
            {
                "id": r.id,
                "tool": r.tool,
                "args": (r.args or "")[:500],
                "session": r.session_id,
                "created": str(r.created_at),
            }
            for r in rows
        ]


def decide(aid: str, approved: bool, owner_user_id: str = "default") -> bool:
    _ensure_table()
    SessionLocal = _SessionLocal()
    with SessionLocal() as db:
        from src.core.db.models import PendingApproval

        pa = (
            db.query(PendingApproval)
            .filter(
                PendingApproval.id == aid,
                PendingApproval.status == "pending",
                PendingApproval.owner_user_id == owner_user_id,
            )
            .first()
        )
        if not pa:
            return False
        pa.status = "approved" if approved else "denied"
        pa.decided_at = db.execute(__import__("sqlalchemy").func.now()).scalar()
        db.commit()
        return True
