"""Orchestrator utama sistem Multi-Agent AI dengan tantangan eksekusi otonom."""

import threading
import time
from dotenv import load_dotenv

# Patch redis to force RESP2 protocol for compatibility with old Redis server
from core.redis_patch import apply_redis_patch

apply_redis_patch()

from agents.agent_executor import run_agent_executor
from mcp_core.registry import load_mcp_context
from mcp_core.context_loader import get_full_agent_context
from core.logger import setup_logger
from config.routing_keywords_pg import get_routing_keywords
from core.adaptive_router import classify_agent
from mcp_core.tool_validator import validate_tools_for_agent

load_dotenv()

logger = setup_logger("orchestrator")
api_lock = threading.Lock()


def route_request(user_input: str, session_id: str) -> str:
    """Route permintaan ke sub-agen yang sesuai berdasarkan kata kunci dengan Rate Limiting."""
    lowered = user_input.lower()

    # Kirim user_input ke context_loader agar RAG bekerja
    full_context = get_full_agent_context(user_input)
    rules_text = full_context.get("rules_text", "")
    skills_text = full_context.get("skills_text", "")
    # Batasi panjang konteks untuk mengurangi beban API
    rules_text = rules_text[:400]
    skills_text = skills_text[:400]

    with api_lock:
        time.sleep(3)

        # Adaptive routing dengan LLM classifier + fallback keyword
        agent_type = classify_agent(user_input)

        system_prompt, tools = load_mcp_context(agent_type)
        tools = validate_tools_for_agent(agent_type, tools)

        augmented_prompt = (
            system_prompt
            + "\n\n=== RULES ===\n"
            + rules_text
            + "\n\n=== SKILLS ===\n"
            + skills_text
        )

        logger.info(
            f"[{session_id}] Context loaded: rules={len(rules_text)} chars, skills={len(skills_text)} chars"
        )
        logger.info(
            f"[{session_id}] -> Routing ke {agent_type.replace('_', ' ').title()} Agent | Tools: {[t.name for t in tools]}"
        )

        from tools.rag_engine import get_relevant_context

        # Turunkan beban RAG sementara untuk mengurangi timeout NVIDIA
        # context = get_relevant_context(user_input, k=2)
        context = ""

        return run_agent_executor(
            user_input=user_input,
            session_id=session_id,
            system_prompt=augmented_prompt,
            tools=tools,
            context=context,
        )


if __name__ == "__main__":
    logger.info("=== Multi-Agent System | Fase 9: Agent Executor with LangGraph ===")
    logger.info("")

    logger.info("--- Tantangan 1: Pembuatan File Otonom oleh Coder Agent ---")
    route_request(
        session_id="session_1_coder",
        user_input="Tolong buatkan sebuah file Python bernama kalkulator.py di root direktori yang berisi fungsi pertambahan sederhana. Kamu WAJIB menggunakan tool tulis_kode untuk menyimpan file tersebut secara nyata ke komputerku.",
    )
    logger.info("")

    logger.info("--- Tantangan 2: Pencarian Web oleh Admin Agent ---")
    route_request(
        session_id="session_2_admin",
        user_input="Buatkan draf surat resmi kepada karyawan tentang penyesuaian gaji UMK Subang tahun 2025. Gunakan bahasa birokrasi yang formal.",
    )
    logger.info("")

    logger.info("--- Tantangan 3: Obrolan Santai oleh Casual Agent ---")
    route_request(
        session_id="session_3_chat",
        user_input="Halo, ada yang bisa bantu? Apa kabar hari ini?",
    )
    logger.info("")

    logger.info("=== Selesai ===")
