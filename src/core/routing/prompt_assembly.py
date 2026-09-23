"""Prompt assembly for routing engine."""

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.router.prompt_assembly")


def _build_augmented_prompt(
    system_prompt: str,
    skill_block: str,
    user_input: str,
    session_id: str,
    agent_type: str,
) -> str:
    """Build augmented system prompt with skill, preferences, RAG, projects, monologue."""
    augmented_prompt = system_prompt + skill_block

    try:
        from src.plugins.core_tools import get_preferences_block

        _pref_block = get_preferences_block()
        if _pref_block:
            augmented_prompt += f"\n\n## {_pref_block}"
    except Exception as _e:
        logger.debug("Preferences block error: %s", _e)

    try:
        from src.mcp_core.retrieval import build_references

        _ref_block = build_references(user_input)
        if _ref_block:
            augmented_prompt += f"\n\n{_ref_block}"
    except Exception as _e:
        logger.debug("RAG references error: %s", _e)

    try:
        from src.plugins.projects import get_projects_block

        _proj_block = get_projects_block()
        if _proj_block:
            augmented_prompt += f"\n\n## {_proj_block}"
    except Exception as _e:
        logger.debug("Projects block error: %s", _e)

    try:
        from src.core.memory.monologue import get_latest_monologue, get_role_for_agent

        latest_monologue = get_latest_monologue(session_id, agent_type)
        if latest_monologue:
            role = latest_monologue.role
            monologue_content = latest_monologue.content
            augmented_prompt += f"\n\n## Monologue ({role})\n{monologue_content}"
        else:
            role = get_role_for_agent(agent_type)
            augmented_prompt += f"\n\n## Monologue ({role})\n[No monologue yet.]"
    except Exception as _e:
        logger.debug("Monologue load error: %s", _e)

    return augmented_prompt
