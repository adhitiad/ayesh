"""LLM shortcut path — direct LLM call without LangGraph tool loop."""

import time

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.shortcut")


def llm_shortcut(
    user_input: str,
    session_id: str,
    augmented_prompt: str,
    agent_type: str,
    skill_name,
    session_nama,
    session_context,
    sess_info: dict,
    t_start: float,
) -> dict | None:
    """Direct LLM call when no tools needed. Returns response dict or None on failure."""
    from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

    from src.agents.llm_config import bind_native_tools
    from src.core.llm.text import extract_text
    from src.core.memory.sessions import (
        generate_session_name_context,
        update_session,
    )

    try:
        from src.memory.memory import get_memory_for_session

        memory = get_memory_for_session(session_id)

        # Per-user LLM: pakai config user jika ada
        from src.core.auth.auth_context import get_current_user_llm_config
        from src.core.llm.task_routing import classify_task, get_llm_for_task

        user_llm_cfg = get_current_user_llm_config()
        if user_llm_cfg and user_llm_cfg.api_key:
            from src.core.llm.factory import get_llm_for_user

            llm = get_llm_for_user(user_llm_cfg)
        else:
            llm = get_llm_for_task(classify_task(agent_type, user_input), agent_type, user_input)
        llm = bind_native_tools(llm)
        messages: list[BaseMessage] = [SystemMessage(content=augmented_prompt)]
        messages.extend(memory.messages)
        messages.append(HumanMessage(content=user_input))

        response = llm.invoke(messages)
        try:
            from src.core.observability.usage import note_usage

            note_usage(response)
        except Exception as _e:
            logger.debug("note_usage error: %s", _e)

        answer = extract_text(response.content if hasattr(response, "content") else str(response))
        elapsed = round(time.time() - t_start, 2)

        memory.add_user_message(user_input)
        memory.add_ai_message(answer)

        if not session_nama:
            new_nama, new_context = generate_session_name_context(user_input, answer)
            if new_nama:
                update_session(
                    session_id,
                    nama=new_nama,
                    context=new_context,
                    agent_type=agent_type,
                )
                session_nama = new_nama
                session_context = new_context

        logger.info("[%s] Selesai dalam %ss", session_id, elapsed)
        return {
            "answer": answer,
            "agent_type": agent_type,
            "tools_used": [],
            "shortcut": True,
            "auto_learned": False,
            "session_id": session_id,
            "session_nama": session_nama,
            "session_context": session_context,
            "skill_invoked": skill_name,
            "process_time": elapsed,
        }
    except Exception as e:
        logger.error("[%s] Shortcut LLM gagal: %s", session_id, e)
        if "429" in str(e) or "Too Many Requests" in str(e):
            raise
        return None
