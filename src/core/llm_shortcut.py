"""LLM shortcut path — direct LLM call without LangGraph tool loop."""

import time

from src.core.logger import setup_logger

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
    from langchain_core.messages import SystemMessage, HumanMessage
    from src.agents.llm_config import get_llm, bind_native_tools
    from src.core.text import extract_text
    from src.core.sessions import (
        get_or_create_session,
        update_session,
        generate_session_name_context,
    )

    try:
        from src.memory.memory import get_memory_for_session

        memory = get_memory_for_session(session_id)

        llm = get_llm()
        llm = bind_native_tools(llm)
        messages = [SystemMessage(content=augmented_prompt)]
        messages.extend(memory.messages)
        messages.append(HumanMessage(content=user_input))

        response = llm.invoke(messages)
        try:
            from src.core.usage import note_usage

            note_usage(response)
        except Exception as _e:
            logger.debug("note_usage error: %s", _e)

        answer = extract_text(
            response.content if hasattr(response, "content") else str(response)
        )
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
