from agents.llm_config import get_llm
from config.routing_keywords_pg import get_routing_keywords

def classify_agent(user_input: str) -> str:
    """Adaptive routing menggunakan LLM classifier."""
    keywords_dict, default_agent = get_routing_keywords()
    
    # Buat prompt classifier
    agents_desc = "\n".join([
        f"- {agent}: {', '.join(kws[:10])}..."
        for agent, kws in keywords_dict.items()
    ])
    
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
        # Validasi hasil
        if result in keywords_dict or result == default_agent:
            return result
        return default_agent
    except Exception:
        # Fallback ke keyword matching
        lowered = user_input.lower()
        for agent, keywords in keywords_dict.items():
            if any(kw in lowered for kw in keywords):
                return agent
        return default_agent
