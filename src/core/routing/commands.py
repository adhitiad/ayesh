"""Slash command handlers — /bantuan, /ringkas, /model."""

import time

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.commands")


def handle_bantuan(session_id: str, sess_info: dict, t_start: float) -> dict:
    """Handle /bantuan command. Returns response dict or None."""
    from src.config.rules import SUBAGENTS
    from src.mcp_core.skills import list_skills

    lines = [
        "Aku adalah Ayesh, agent AI yang dibuat dengan cinta.",
        "",
        "Perintah yang tersedia:",
        "",
        "Skill (ketik /nama-skill + pesan):",
    ]
    for s in list_skills():
        lines.append(f"- /{s['name']}: {s['description']}")
    lines.append("")
    lines.append("Agent (otomatis via keyword):")
    for name, cfg in SUBAGENTS.items():
        lines.append(f"- {name}: {cfg['when_to_use']}")
    lines += [
        "",
        "Session:",
        "- /model provider:model: ganti model LLM (contoh: /model groq:llama-3.3-70b-versatile).",
        "- /model provider:model --session: ganti model untuk session ini saja (tidak disimpan).",
        "- /ringkas: ringkas percakapan session ini sekarang.",
        "- /bantuan: tampilkan pesan ini.",
        "",
        "Contoh:",
        "- /surat-resmi buatkan izin cuti 3 hari",
        "- /koding buatkan file hello.py",
    ]
    elapsed = round(time.time() - t_start, 2)
    return {
        "answer": "\n".join(lines),
        "agent_type": "casual_agent",
        "tools_used": [],
        "shortcut": True,
        "auto_learned": False,
        "session_id": session_id,
        "session_nama": sess_info.get("nama"),
        "session_context": sess_info.get("context"),
        "skill_invoked": None,
        "process_time": elapsed,
    }


def handle_ringkas(session_id: str, sess_info: dict, t_start: float) -> dict:
    """Handle /ringkas command. Returns response dict or None."""
    from src.memory.memory import get_memory_for_session

    summary = get_memory_for_session(session_id).force_summarize()
    elapsed = round(time.time() - t_start, 2)
    answer = summary if summary else "Belum cukup pesan untuk diringkas (butuh 20 pesan tersimpan)."
    logger.info(
        "[%s] /ringkas: %s",
        session_id,
        "ringkasan dibuat" if summary else "belum cukup pesan",
    )
    return {
        "answer": answer,
        "agent_type": "casual_agent",
        "tools_used": [],
        "shortcut": True,
        "auto_learned": False,
        "session_id": session_id,
        "session_nama": sess_info.get("nama"),
        "session_context": sess_info.get("context"),
        "skill_invoked": None,
        "process_time": elapsed,
    }


def handle_model(user_input: str, user_id: str, session_id: str, sess_info: dict, t_start: float) -> dict:
    """Handle /model command. /model provider:model_name untuk switch model per-session.

    Contoh:
      /model groq:llama-3.3-70b-versatile          (simpan sebagai default)
      /model openai:gpt-4o-mini --session           (hanya untuk session ini)
      /model google:gemini-2.5-flash                (simpan sebagai default)
      /model                                        (tampilkan model aktif)
    """
    from src.core.auth.auth import add_user_llm_config, list_user_llm_configs, update_user_llm_config_entry
    from src.core.auth.auth_context import UserLLMConfig, get_current_user_llm_config, set_current_user_llm_config

    parts = user_input.strip().split(None, 1)
    elapsed = round(time.time() - t_start, 2)

    # Tampilkan model aktif jika tidak ada argumen
    if len(parts) < 2 or not parts[1].strip():
        current = get_current_user_llm_config()
        if current and current.api_key:
            answer = (
                f"Model aktif: **{current.provider}:{current.model}**\n"
                f"Temperature: {current.temperature or 0.7}\n\n"
                "Ganti: `/model provider:model_name` (contoh: `/model groq:llama-3.3-70b-versatile`)\n"
                "Session-only: `/model provider:model_name --session` (tidak disimpan)"
            )
        else:
            answer = (
                "Model aktif: **global default** (belum set model personal)\n\n"
                "Set model: `/model provider:model_name`\n"
                "Session-only: `/model provider:model_name --session` (tidak disimpan)\n"
                "Contoh: `/model groq:llama-3.3-70b-versatile`"
            )
        return _model_response(answer, session_id, sess_info, elapsed)

    spec = parts[1].strip()
    session_only = "--session" in spec
    if session_only:
        spec = spec.replace("--session", "").strip()

    if ":" not in spec:
        answer = "Format salah. Gunakan: `/model provider:model_name`\nContoh: `/model groq:llama-3.3-70b-versatile`"
        return _model_response(answer, session_id, sess_info, elapsed)

    provider, model = spec.split(":", 1)
    provider = provider.strip().lower()
    model = model.strip()

    if not provider or not model:
        answer = "Format salah. Gunakan: `/model provider:model_name`"
        return _model_response(answer, session_id, sess_info, elapsed)

    # Provider validation
    valid_providers = {"nvidia", "groq", "google", "openai", "anthropic", "ollama", "deepseek", "grok"}
    if provider not in valid_providers:
        answer = f"Provider '{provider}' tidak dikenal.\nPilihan: {', '.join(sorted(valid_providers))}"
        return _model_response(answer, session_id, sess_info, elapsed)

    try:
        if session_only:
            # Session-only: set ContextVar saja, tidak persist ke DB
            # Bawa api_key dari config existing agar model benar-benar dipakai
            current = get_current_user_llm_config()
            api_key = current.api_key if current else None
            set_current_user_llm_config(UserLLMConfig(provider=provider, model=model, api_key=api_key))
            answer = f"Model session diubah ke **{provider}:{model}**\nBerlaku untuk session ini saja (tidak disimpan)."
            logger.info(
                "[%s] /model --session: user %s pakai %s:%s (session-only)", session_id, user_id, provider, model
            )
        else:
            # Persist ke DB: cari config existing dengan provider+model yang sama, atau buat baru
            configs = list_user_llm_configs(user_id)
            existing = None
            for c in configs:
                if c["provider"] == provider and c["model"] == model:
                    existing = c
                    break

            if existing:
                update_user_llm_config_entry(user_id, existing["id"], is_default=True)
            else:
                add_user_llm_config(user_id, provider=provider, model=model, is_default=True)

            # Update ContextVar — load api_key dari config existing
            from src.core.auth.auth_keys import get_user_default_llm

            llm_data = get_user_default_llm(user_id)
            api_key = llm_data["api_key"] if llm_data else None
            set_current_user_llm_config(UserLLMConfig(provider=provider, model=model, api_key=api_key))

            answer = f"Model diubah ke **{provider}:{model}**\nKonfigurasi disimpan sebagai default untuk akunmu."
            logger.info("[%s] /model: user %s switch ke %s:%s", session_id, user_id, provider, model)
    except Exception as e:
        logger.error("[%s] /model error: %s", session_id, e)
        answer = f"Gagal mengubah model: {e}"

    return _model_response(answer, session_id, sess_info, elapsed)


def _model_response(answer: str, session_id: str, sess_info: dict, elapsed: float) -> dict:
    return {
        "answer": answer,
        "agent_type": "casual_agent",
        "tools_used": [],
        "shortcut": True,
        "auto_learned": False,
        "session_id": session_id,
        "session_nama": sess_info.get("nama"),
        "session_context": sess_info.get("context"),
        "skill_invoked": None,
        "process_time": elapsed,
    }
