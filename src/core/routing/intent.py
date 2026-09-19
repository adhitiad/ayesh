"""Intent detection and keyword learning via LLM."""

import json
import re

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.intent")


def detect_actionable_intent(user_input: str) -> bool:
    """Deteksi apakah input user memiliki intent actionable (butuh tool) tapi tidak ter-detect."""
    lowered = user_input.lower()
    actionable_patterns = [
        "carikan",
        "cari ",
        "carilah",
        "buatkan",
        "buat ",
        "buatlah",
        "tulis",
        "tuliskan",
        "harga ",
        "harga",
        "biaya",
        "biayanya",
        "info ",
        "informasi",
        "berita",
        "terbaru",
        "update",
        "saham",
        "crypto",
        "bitcoin",
        "ethereum",
        "emas",
        "dolar",
        "kurs",
        "cuaca",
        "prakiraan",
        "jadwal",
        "waktu",
        "definisi",
        "arti ",
        "pengertian",
        "tutorial",
        "cara ",
        "bagaimana ",
        "script",
        "kode",
        "fungsi",
        "program",
        "python",
        "javascript",
        "deploy",
        "install",
        "setup",
    ]
    return any(p in lowered for p in actionable_patterns)


def auto_learn_keyword(
    user_input: str, session_id: str
) -> tuple[str, str, list] | None:
    """Gunakan LLM untuk menentukan agent, keyword, dan tools yang tepat, lalu simpan ke DB."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.agents.llm_config import get_llm
        from src.config.routing_keywords_pg import (
            add_keyword_with_tools,
            invalidate_routing_cache,
        )
        from src.config.rules import get_agents_block

        llm = get_llm()

        prompt = f"""Analisis permintaan user berikut dan tentukan:
1. Agent yang paling cocok: coder_agent, admin_agent, atau casual_agent
2. Keyword unik (1-3 kata, lowercase) yang merepresentasikan intent
3. Tools yang dibutuhkan: tulis_kode, baca_file, cari_web, get_current_time, minta_review, learn_keyword, atau kosong

{get_agents_block()}


User input: "{user_input}"

Jawab HANYA dengan JSON valid:
{{
  "agent": "coder_agent|admin_agent|casual_agent",
  "keyword": "kata_kunci_unik",
  "allowed_tools": ["tool1", "tool2"]
}}

Contoh:
- "carikan harga emas" -> {{"agent": "admin_agent", "keyword": "harga emas", "allowed_tools": ["cari_web"]}}
- "cek cuaca jakarta besok" -> {{"agent": "admin_agent", "keyword": "cuaca jakarta", "allowed_tools": ["cari_web"]}}
- "buatkan file python hello world" -> {{"agent": "coder_agent", "keyword": "buatkan file python", "allowed_tools": ["tulis_kode", "baca_file"]}}
- "apa kabar" -> {{"agent": "casual_agent", "keyword": "apa kabar", "allowed_tools": []}}"""

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=user_input),
        ]
        response = llm.invoke(messages)
        _raw = response.content if hasattr(response, "content") else str(response)
        content = "\n".join(str(x) for x in _raw) if isinstance(_raw, list) else _raw

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            logger.warning(
                "[%s] Auto-learn: JSON tidak ditemukan di response: %s",
                session_id,
                content,
            )
            return None

        data = json.loads(json_match.group())
        agent = data.get("agent", "").strip().lower()
        keyword = data.get("keyword", "").strip().lower()
        allowed_tools = data.get("allowed_tools", [])

        valid_agents = {"coder_agent", "admin_agent", "casual_agent"}
        if agent not in valid_agents:
            logger.warning("[%s] Auto-learn: Agent tidak valid: %s", session_id, agent)
            return None
        if not keyword or len(keyword) < 2:
            logger.warning(
                "[%s] Auto-learn: Keyword terlalu pendek: %s", session_id, keyword
            )
            return None

        valid_tools = {
            "tulis_kode",
            "baca_file",
            "cari_web",
            "get_current_time",
            "minta_review",
            "learn_keyword",
        }
        allowed_tools = [t for t in allowed_tools if t in valid_tools]

        ok = add_keyword_with_tools(agent, keyword, allowed_tools)
        if ok:
            invalidate_routing_cache()
            logger.info(
                "[%s] Auto-learn: Berhasil simpan '%s' -> %s (tools: %s)",
                session_id,
                keyword,
                agent,
                allowed_tools,
            )
            return agent, keyword, allowed_tools
        else:
            logger.warning("[%s] Auto-learn: Gagal simpan ke DB", session_id)
            return None

    except Exception as e:
        logger.error("[%s] Auto-learn error: %s", session_id, e)
        return None
