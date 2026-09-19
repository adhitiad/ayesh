from src.agents.llm_config import get_llm
from src.config.routing_keywords_pg import get_routing_keywords


def _record_routing_monologue(user_id, agent, user_input, method):
    """Tulis monologue per klasifikasi routing. Gagal tulis tidak boleh ganggu routing."""
    if not user_id:
        return
    try:
        from src.core.monologue import add_monologue, get_role_for_agent

        role = get_role_for_agent(agent)
        content = (
            f"Routing '{user_input[:120]}' -> {agent} via {method} (role: {role})."
        )
        add_monologue(user_id, agent, role, content)
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("get_agent_for_input error: %s", _e)


def classify_agent(user_input: str, user_id: str | None = None) -> str:
    """Routing berbasis keyword dulu, LLM sebagai fallback.

    Setiap hasil klasifikasi ditulis sebagai monologue per user_id
    (bila user_id diisi) dengan role sesuai agent_type.
    """
    keywords_dict, default_agent = get_routing_keywords()

    # 1. Keyword matching (cepat, tanpa LLM)
    lowered = user_input.lower()
    for agent, keywords in keywords_dict.items():
        for kw in keywords:
            if kw in lowered:
                _record_routing_monologue(user_id, agent, user_input, f"keyword:{kw}")
                return agent

    # 2. Fallback ke LLM jika tidak ada keyword match
    agents_desc = "\n".join(
        [f"- {agent}: {', '.join(kws[:10])}..." for agent, kws in keywords_dict.items()]
    )

    prompt = f"""
Tugasmu adalah mengklasifikasikan input user ke salah satu agen berikut:
{agents_desc}
Default: {default_agent}

Input user: "{user_input}"

Jawab hanya dengan nama agen: coder_agent, admin_agent, atau casual_agent
"""
    try:
        llm = get_llm()
        result = llm.invoke(prompt).content.strip().lower()
        if result in keywords_dict or result == default_agent:
            _record_routing_monologue(user_id, result, user_input, "llm-fallback")
            return result
        _record_routing_monologue(user_id, default_agent, user_input, "llm-default")
        return default_agent
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("adaptive routing error: %s", _e)
        _record_routing_monologue(user_id, default_agent, user_input, "error-default")
        return default_agent
