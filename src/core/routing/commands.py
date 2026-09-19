"""Slash command handlers — /bantuan and /ringkas."""

import time

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.commands")


def handle_bantuan(session_id: str, sess_info: dict, t_start: float) -> dict | None:
    """Handle /bantuan command. Returns response dict or None."""
    from src.config.rules import SUBAGENTS
    from src.mcp_core.skills import list_skills

    lines = [
        "Aku adalah Ayesh, agent AI yang dibuat dengan cinta.",
        "",
        "Perintah yang tersedia:",
        "",
        "Skill (ketik /nama-skill + pesan):",
    ]
    for s in list_skills():
        lines.append(f"- /{s['name']}: {s['description']}")
    lines.append("")
    lines.append("Agent (otomatis via keyword):")
    for name, cfg in SUBAGENTS.items():
        lines.append(f"- {name}: {cfg['when_to_use']}")
    lines += [
        "",
        "Session:",
        "- /ringkas: ringkas percakapan session ini sekarang.",
        "- /bantuan: tampilkan pesan ini.",
        "",
        "Contoh:",
        "- /surat-resmi buatkan izin cuti 3 hari",
        "- /koding buatkan file hello.py",
    ]
    elapsed = round(time.time() - t_start, 2)
    return {
        "answer": "\n".join(lines),
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


def handle_ringkas(session_id: str, sess_info: dict, t_start: float) -> dict | None:
    """Handle /ringkas command. Returns response dict or None."""
    from src.memory.memory import get_memory_for_session

    summary = get_memory_for_session(session_id).force_summarize()
    elapsed = round(time.time() - t_start, 2)
    answer = (
        summary
        if summary
        else "Belum cukup pesan untuk diringkas (butuh 20 pesan tersimpan)."
    )
    logger.info(
        "[%s] /ringkas: %s",
        session_id,
        "ringkasan dibuat" if summary else "belum cukup pesan",
    )
    return {
        "answer": answer,
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
