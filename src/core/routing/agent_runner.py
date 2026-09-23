"""Full agent execution with auto-retry."""

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.router.agent_runner")


def _run_full_agent(
    user_input: str,
    session_id: str,
    augmented_prompt: str,
    validated_tools: list,
    agent_type: str,
    skill_name,
    session_nama,
    session_context,
    sess_info: dict,
    used_auto_learn: bool,
    t_start: float,
) -> dict:
    """Run full agent executor path with auto-retry on tool failure."""
    from src.agents.agent_executor import run_agent_executor
    from src.core.memory.sessions import generate_session_name_context, update_session
    from src.core.routing.responses import _build_response
    from src.core.routing.tools import learn_from_tool_failure, log_tool_failure
    from src.plugins.core_tools import AVAILABLE_PLUGINS

    answer: str | None = None
    for _attempt in range(2):
        try:
            answer = run_agent_executor(
                user_input=user_input,
                session_id=session_id,
                system_prompt=augmented_prompt,
                tools=validated_tools,
                context="",
            )
            break
        except Exception as e:
            tool_names = [t.name for t in validated_tools]
            for t_name in tool_names:
                log_tool_failure(t_name, str(e), agent_type, session_id, user_input[:50])
            if _attempt == 0:
                swapped, replaced = [], set()
                for t_name in tool_names:
                    alt = learn_from_tool_failure(t_name, agent_type, session_id, user_input)
                    for a in alt or []:
                        if a in AVAILABLE_PLUGINS and a not in tool_names and a not in replaced:
                            swapped.append(AVAILABLE_PLUGINS[a])
                            replaced.add(a)
                    if alt:
                        replaced.add(t_name)
                if swapped:
                    logger.info(
                        "[%s] Retry dengan tool alternatif: %s",
                        session_id,
                        [t.name for t in swapped],
                    )
                    validated_tools = [t for t in validated_tools if t.name not in replaced] + swapped
                    if validated_tools:
                        continue
            raise

    if not session_nama:
        new_nama, new_context = generate_session_name_context(user_input, answer or "")
        if new_nama:
            update_session(session_id, nama=new_nama, context=new_context, agent_type=agent_type)
            session_nama = new_nama
            session_context = new_context

    return _build_response(
        answer=answer,
        agent_type=agent_type,
        session_id=session_id,
        session_nama=session_nama,
        session_context=session_context,
        skill_name=skill_name,
        tools_used=[t.name for t in validated_tools],
        shortcut=False,
        auto_learned=used_auto_learn,
        t_start=t_start,
    )
