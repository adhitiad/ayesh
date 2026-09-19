"""Skill invocation parsing — Claude Code-style /nama-skill prefix."""

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.skills")


def extract_skill_invocation(user_input: str) -> tuple:
    """Parse prefix /nama-skill ala Claude Code. Return (skill_name|None, sisa_input, unknown|None)."""
    text = user_input.strip()
    if not text.startswith("/"):
        return None, user_input, None
    parts = text.split(None, 1)
    name = parts[0][1:].lower()
    rest = parts[1] if len(parts) > 1 else ""
    from src.mcp_core.skills import load_skill

    if load_skill(name) is None:
        return None, user_input, name
    return name, rest, None


def split_fanout_segments(user_input: str) -> list:
    """Pecah pesan multi-skill jadi [(skill, teks)]. [] bila <2 skill dikenal."""
    import re

    from src.mcp_core.skills import load_skill

    found = [
        (m.start(), m.group(1).lower()) for m in re.finditer(r"/([\w-]+)", user_input)
    ]
    found = [(pos, name) for pos, name in found if load_skill(name) is not None]
    if len(found) < 2:
        return []
    segments = []
    for i, (pos, name) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(user_input)
        text = user_input[pos:end].strip()
        text = re.sub(r"^/[\w-]+\s*", "", text).strip()
        segments.append((name, text or "(tanpa detail tambahan)"))
    return segments
