"""Main routing engine — orchestrates all core modules to process user requests.

Thin re-export layer: implementation moved to submodules for line-count compliance.
"""

import time

from src.core.observability.logger import setup_logger

# ── Re-export helpers from submodules ──────────────────────────────────
from src.core.routing.agent_runner import _run_full_agent
from src.core.routing.prompt_assembly import _build_augmented_prompt
from src.core.routing.responses import (
    _handle_injection_blocked,
    _handle_unknown_skill,
)
from src.core.routing.session_affinity import _apply_session_affinity

logger = setup_logger("orchestrator.router")


def _load_user_llm_config(user_id: str) -> None:
    """Load per-user default LLM config + skill/MCP overrides dari tabel relasi ke ContextVar."""
    from src.core.auth.auth_context import (
        UserLLMConfig,
        set_current_user_llm_config,
        set_disabled_mcp,
        set_disabled_skills,
    )
    from src.core.auth.auth_keys import get_user_default_llm, list_user_mcp_overrides, list_user_skill_overrides

    if not user_id or user_id == "default":
        return

    try:
        llm_data = get_user_default_llm(user_id)
        if llm_data and llm_data.get("api_key"):
            set_current_user_llm_config(
                UserLLMConfig(
                    provider=llm_data["provider"],
                    api_key=llm_data["api_key"],
                    model=llm_data["model"],
                    temperature=llm_data["temperature"],
                )
            )
    except Exception as e:
        logger.debug("Gagal load LLM config user %s: %s", user_id, e)

    try:
        skill_overrides = list_user_skill_overrides(user_id)
        disabled = {o["skill_name"] for o in skill_overrides if not o["enabled"]}
        set_disabled_skills(frozenset(disabled))
    except Exception as e:
        logger.debug("Gagal load skill overrides user %s: %s", user_id, e)

    try:
        mcp_overrides = list_user_mcp_overrides(user_id)
        disabled = {o["mcp_name"] for o in mcp_overrides if not o["enabled"]}
        set_disabled_mcp(frozenset(disabled))
    except Exception as e:
        logger.debug("Gagal load MCP overrides user %s: %s", user_id, e)


def _cleanup_user_context() -> None:
    """Reset ContextVar per-user setelah request selesai agar tidak bocor ke request berikutnya."""
    from src.core.auth.auth_context import (
        set_current_user_llm_config,
        set_disabled_mcp,
        set_disabled_skills,
    )

    set_current_user_llm_config(None)
    set_disabled_skills(frozenset())
    set_disabled_mcp(frozenset())


def route_request_inner(
    user_input: str,
    session_id: str,
    _depth: int = 0,
    request_id: str | None = None,
) -> dict:
    """Isi route_request (dipisah agar decorator metrik tidak ganggu rekursi fan-out)."""
    from src.core.auth.approval import set_current_owner_user_id, set_current_session
    from src.core.auth.auth import get_current_user_id
    from src.core.llm.llm_shortcut import llm_shortcut
    from src.core.memory.learning import process_pending_learnings
    from src.core.memory.sessions import get_or_create_session
    from src.core.observability.logger import get_request_id, set_request_id, set_session_id
    from src.core.routing.adaptive_router import classify_agent
    from src.core.routing.commands import handle_bantuan, handle_model, handle_ringkas
    from src.core.routing.fanout import route_fanout
    from src.core.routing.intent import auto_learn_keyword, detect_actionable_intent
    from src.core.routing.skills import extract_skill_invocation, split_fanout_segments
    from src.core.routing.tools import filter_tools_by_keywords, get_quarantined_tools

    # Request/session ID tracing: seed ContextVar agar semua log JSON di jalur ini
    # membawa request_id yang sama (tanpa mengubah signature logger).
    from src.core.system.error_handling import generate_request_id
    from src.mcp_core.registry import load_mcp_context
    from src.mcp_core.tool_validator import filter_tool_names_for_agent, validate_tools_for_agent
    from src.plugins.core_tools import AVAILABLE_PLUGINS
    from src.plugins.input_guard import validate_user_input

    rid = request_id or get_request_id() or generate_request_id()
    set_request_id(rid)
    set_session_id(session_id)

    t_start = time.time()

    try:
        # Input sanitization & prompt injection guard
        valid, sanitized = validate_user_input(user_input)
        if not valid:
            return _handle_injection_blocked(session_id, sanitized, t_start)
        user_input = sanitized

        try:
            set_current_session(session_id)
        except Exception as _e:
            logger.debug("set_current_session error: %s", _e)

        # Rate limiting ditangani di lapisan HTTP (src/core/system/rate_limit.py + middleware).
        # Blok TokenBucket per-session legacy dihapus — modulnya (rate_limiter) tidak lagi ada
        # sejak refactor src/core menjadi subfolder (rate_limit.py), dan setiap pemanggilan
        # route_request_inner akan ImportError/500.
        user_id = get_current_user_id()
        set_current_owner_user_id(user_id)
        sess_info = get_or_create_session(session_id, user_id, user_id)

        # Load per-user LLM config ke ContextVar (bila user punya api_key/model sendiri)
        _load_user_llm_config(user_id)

        # Perintah bawaan (tanpa LLM routing)
        _text = user_input.strip()
        if _text.startswith("/bantuan"):
            return handle_bantuan(session_id, sess_info, t_start)
        if _text.startswith("/ringkas"):
            return handle_ringkas(session_id, sess_info, t_start)
        if _text.startswith("/model"):
            return handle_model(user_input, user_id, session_id, sess_info, t_start)

        # Fan-out: pesan berisi >=2 skill dikenal -> paralel + sintesis (depth-0 saja)
        if _depth == 0:
            _segments = split_fanout_segments(user_input)
            if _segments:
                logger.info("[%s] Fan-out: %s", session_id, [s for s, _ in _segments])
                return route_fanout(user_input, session_id, _segments)

        # Skill invocation ala Claude Code: /nama-skill <sisa pesan>
        skill_name, user_input, unknown_skill = extract_skill_invocation(user_input)
        skill_block = ""
        if unknown_skill:
            return _handle_unknown_skill(unknown_skill, session_id, sess_info, t_start)
        if skill_name:
            from src.mcp_core.skills import load_skill

            skill = load_skill(skill_name)
            if skill:
                skill_block = f"\n\n## Invoked skill: /{skill_name}\n{skill['body']}"
                logger.info("[%s] Skill invoked: /%s", session_id, skill_name)

        # Proses feedback learning secara periodik
        if hash(session_id) % 50 == 0:
            process_pending_learnings()

        agent_type = classify_agent(user_input, user_id=session_id)
        _classified_agent = agent_type

        # Session affinity
        agent_type = _apply_session_affinity(agent_type, user_input, session_id, sess_info, _classified_agent)

        system_prompt, _default_tools = load_mcp_context(
            agent_type,
            session_nama=sess_info.get("nama"),
            session_context=sess_info.get("context"),
        )
        filtered_tools = filter_tools_by_keywords(agent_type, user_input)
        validated_tools = validate_tools_for_agent(agent_type, filtered_tools)

        # Build augmented prompt
        augmented_prompt = _build_augmented_prompt(system_prompt, skill_block, user_input, session_id, agent_type)

        logger.info(
            "[%s] -> Routing ke %s | Tools: %s",
            session_id,
            agent_type.replace("_", " ").title(),
            [t.name for t in validated_tools],
        )

        # Auto-learn
        used_auto_learn = False
        if agent_type == "casual_agent" and not validated_tools and detect_actionable_intent(user_input):
            logger.info(
                "[%s] Auto-learn: Terdeteksi intent actionable, mempelajari keyword baru...",
                session_id,
            )
            learned = auto_learn_keyword(user_input, session_id)
            if learned:
                learned_agent, _learned_keyword, learned_tools = learned
                logger.info(
                    "[%s] Auto-learn: Berhasil, menggunakan tools yang baru dipelajari...",
                    session_id,
                )
                learned_tools = filter_tool_names_for_agent(learned_agent, learned_tools)
                validated_tools = []
                for tool_name in learned_tools:
                    if tool_name in AVAILABLE_PLUGINS:
                        validated_tools.append(AVAILABLE_PLUGINS[tool_name])
                agent_type = learned_agent
                used_auto_learn = True

        # Karantina
        _quarantined = get_quarantined_tools()
        if _quarantined:
            _kept = [t for t in validated_tools if t.name not in _quarantined]
            if _kept:
                _dropped = sorted({t.name for t in validated_tools} - {t.name for t in _kept})
                logger.info("[%s] Karantina tool gagal berulang: %s", session_id, _dropped)
                validated_tools = _kept

        session_nama = sess_info.get("nama")
        session_context = sess_info.get("context")

        # Shortcut: tidak ada tools -> LLM langsung
        if not validated_tools:
            logger.info("[%s] Shortcut: tidak ada tools, panggil LLM langsung.", session_id)
            result = llm_shortcut(
                user_input,
                session_id,
                augmented_prompt,
                agent_type,
                skill_name,
                session_nama,
                session_context,
                sess_info,
                t_start,
            )
            if result is not None:
                return result

        # Full path: agent executor dengan tool calling loop + 1x auto-retry
        return _run_full_agent(
            user_input,
            session_id,
            augmented_prompt,
            validated_tools,
            agent_type,
            skill_name,
            session_nama,
            session_context,
            sess_info,
            used_auto_learn,
            t_start,
        )
    finally:
        _cleanup_user_context()
