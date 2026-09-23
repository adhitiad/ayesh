"""Tool validator: SINGLE authority for agent → tool capability mapping.

P1.5 — TOOL_CAPABILITIES is the ONLY source of truth for which tools each
agent can use. Validator can only NARROW (intersect with runtime tools),
never expand. AGENT_RULES['skills'] is documentation/trigger info, NOT
a security capability grant.
"""

# === SINGLE AUTHORITY: Security capability per agent ===
# This is the ONLY place that defines which tools each agent may execute.
# AGENT_RULES['skills'] = documentation/trigger hints (NOT security boundary).
TOOL_CAPABILITIES: dict[str, set[str]] = {
    "coder_agent": {
        "tulis_kode",
        "baca_file",
        "learn_keyword",
        "get_current_time",
        "minta_review",
        "baca_url",
        "jalankan_python",
        "panggil_mcp",
        "ingat_fakta",
        "lihat_fakta",
        "cari_fakta",
        "lihat_preferensi",
        "simpan_proyek",
        "catat_proyek",
        "lihat_proyek",
        "info_sistem",
        "set_target_dir",
        "ingat_preferensi",
        "buat_plan",
        "lihat_plan",
        "cari_plan",
        "jalankan_langkah",
        "tandai_selesai",
        "batal_plan",
    },
    "admin_agent": {
        "cari_web",
        "get_current_time",
        "minta_review",
        "baca_url",
        "panggil_mcp",
        "ingat_fakta",
        "lihat_fakta",
        "cari_fakta",
        "lihat_preferensi",
        "lihat_proyek",
        "buat_plan",
        "lihat_plan",
        "cari_plan",
        "jalankan_langkah",
        "tandai_selesai",
        "batal_plan",
    },
    "casual_agent": {
        "get_current_time",
        "ingat_fakta",
        "lihat_fakta",
        "cari_fakta",
        "ingat_preferensi",
        "lihat_preferensi",
        "simpan_proyek",
        "catat_proyek",
        "lihat_proyek",
        "buat_plan",
        "lihat_plan",
        "cari_plan",
        "jalankan_langkah",
        "tandai_selesai",
        "batal_plan",
    },
}


def validate_tools_for_agent(agent_type: str, tools: list) -> list:
    """Filter tools: intersect runtime tools with TOOL_CAPABILITIES (single authority).

    Validator can only NARROW. It never adds tools that aren't in
    TOOL_CAPABILITIES, even if AGENT_RULES['skills'] lists them.
    """
    capabilities = TOOL_CAPABILITIES.get(agent_type)
    if capabilities is None:
        return []  # unknown agent → no tools

    filtered = []
    for tool in tools:
        tool_name = getattr(tool, "name", "")
        if tool_name in capabilities:
            filtered.append(tool)
    return filtered


def get_agent_capabilities(agent_type: str) -> set[str]:
    """Return the capability set for the agent (read-only)."""
    return TOOL_CAPABILITIES.get(agent_type, set()).copy()


def filter_tool_names_for_agent(agent_type: str, tool_names: list) -> list:
    """Filter nama tool agar ≤ kapasitas statis agent (narrow-only).

    Dipakai jalur auto-learn (output LLM) sebelum tool diinstansiasi:
    learned tools tidak pernah boleh melebihi TOOL_CAPABILITIES agent.
    Unknown agent → [] (fail-closed).
    """
    capabilities = TOOL_CAPABILITIES.get(agent_type)
    if capabilities is None:
        return []
    return [name for name in tool_names if name in capabilities]
