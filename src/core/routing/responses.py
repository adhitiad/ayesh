"""Response builders for routing engine."""

import time

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.router.responses")


def _build_response(
    answer,
    agent_type: str,
    session_id: str,
    session_nama,
    session_context,
    skill_name,
    tools_used: list,
    shortcut: bool,
    auto_learned: bool,
    t_start: float,
) -> dict:
    """Build standard response dict."""
    return {
        "answer": answer,
        "agent_type": agent_type,
        "tools_used": tools_used,
        "shortcut": shortcut,
        "auto_learned": auto_learned,
        "session_id": session_id,
        "session_nama": session_nama,
        "session_context": session_context,
        "skill_invoked": skill_name,
        "process_time": round(time.time() - t_start, 2),
    }


def _handle_injection_blocked(session_id: str, sanitized: str, t_start: float) -> dict:
    """Build response for blocked prompt injection."""
    logger.warning("[%s] Prompt injection blocked: %s", session_id, sanitized)
    return _build_response(
        answer="Input ditolak: terdeteksi pola prompt injection. Silakan ulangi dengan pertanyaan biasa.",
        agent_type="casual_agent",
        session_id=session_id,
        session_nama=None,
        session_context=None,
        skill_name=None,
        tools_used=[],
        shortcut=True,
        auto_learned=False,
        t_start=t_start,
    )


def _handle_unknown_skill(unknown_skill: str, session_id: str, sess_info: dict, t_start: float) -> dict:
    """Build response for unknown skill."""
    from src.mcp_core.skills import list_skills

    available = ", ".join(f"/{s['name']}" for s in list_skills()) or "(belum ada skill)"
    elapsed = round(time.time() - t_start, 2)
    logger.info("[%s] Skill tidak dikenal: /%s", session_id, unknown_skill)
    return {
        "answer": f"Skill '/{unknown_skill}' tidak dikenal. Skill yang tersedia: {available}.",
        "agent_type": "casual_agent",
        "tools_used": [],
        "shortcut": True,
        "auto_learned": False,
        "session_id": session_id,
        "session_nama": sess_info.get("nama"),
        "session_context": sess_info.get("context"),
        "skill_invoked": None,
        "process_time": elapsed,
    }
