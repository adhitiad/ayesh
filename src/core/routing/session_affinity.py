"""Session affinity logic for routing engine."""

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.router.session_affinity")


def _apply_session_affinity(
    agent_type: str,
    user_input: str,
    session_id: str,
    sess_info: dict,
    classified_agent: str,
) -> str:
    """Apply session affinity — follow-up tanpa keyword match tetap di agent session."""
    try:
        from src.config.routing_keywords_pg import get_routing_keywords
        from src.config.rules import SUBAGENTS

        _kw_dict, _ = get_routing_keywords()
        _lowered = user_input.strip().lower()
        _has_hit = any(kw in _lowered for kws in _kw_dict.values() for kw in kws)
        _prior = sess_info.get("agent_type")
        if not _has_hit and _prior in SUBAGENTS:
            agent_type = _prior
            logger.info(
                "[%s] Afinitas session: tetap %s (tanpa keyword match)",
                session_id,
                agent_type,
            )
    except Exception as _e:
        logger.debug("Session affinity check error: %s", _e)

    try:
        from src.core.memory.sessions import update_session

        update_session(session_id, agent_type=agent_type)
    except Exception as _e:
        logger.debug("update_session error: %s", _e)

    try:
        from src.core.auth.approval import set_current_agent_type

        set_current_agent_type(agent_type)
    except Exception as _e:
        logger.debug("set_current_agent_type error: %s", _e)

    if agent_type != classified_agent:
        try:
            from src.core.memory.monologue import add_monologue, get_role_for_agent

            _role = get_role_for_agent(agent_type)
            add_monologue(
                session_id,
                agent_type,
                _role,
                f"Afinitas session: '{user_input[:120]}' tetap di {agent_type} "
                f"(role: {_role}; router awal: {classified_agent}).",
            )
        except Exception as _e:
            logger.debug("Monologue affinity update error: %s", _e)

    return agent_type
