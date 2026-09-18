from config.rules import AGENT_RULES

# Define allow-list for each agent
AGENT_TOOL_ALLOWLIST = {
    "coder_agent": ["tulis_kode", "baca_file"],
    "admin_agent": ["cari_web"],
    "casual_agent": [],
}

def validate_tools_for_agent(agent_type: str, tools: list):
    """Filter tools berdasarkan allow-list agen (exact name match)."""
    allowed_names = set(AGENT_TOOL_ALLOWLIST.get(agent_type, []))

    # Get skills from AGENT_RULES as fallback
    agent_skills = AGENT_RULES.get(agent_type, {}).get("skills", [])
    allowed_names.update(agent_skills)

    filtered_tools = []
    for tool in tools:
        tool_name = getattr(tool, "name", "")
        if tool_name in allowed_names:
            filtered_tools.append(tool)

    return filtered_tools
