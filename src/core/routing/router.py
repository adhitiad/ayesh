"""Main routing engine — orchestrates all core modules to process user requests."""

import time

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.router")


def _build_response(
    answer,
    agent_type: str,
    session_id: str,
    session_nama,
    session_context,
    skill_name,
    tools_used: list,
    shortcut: bool,
    auto_learned: bool,
    t_start: float,
) -> dict:
    """Build standard response dict."""
    return {
        "answer": answer,
        "agent_type": agent_type,
        "tools_used": tools_used,
        "shortcut": shortcut,
        "auto_learned": auto_learned,
        "session_id": session_id,
        "session_nama": session_nama,
        "session_context": session_context,
        "skill_invoked": skill_name,
        "process_time": round(time.time() - t_start, 2),
    }


def _handle_injection_blocked(session_id: str, sanitized: str, t_start: float) -> dict:
    """Build response for blocked prompt injection."""
    logger.warning("[%s] Prompt injection blocked: %s", session_id, sanitized)
    return _build_response(
        answer="Input ditolak: terdeteksi pola prompt injection. Silakan ulangi dengan pertanyaan biasa.",
        agent_type="casual_agent",
        session_id=session_id,
        session_nama=None,
        session_context=None,
        skill_name=None,
        tools_used=[],
        shortcut=True,
        auto_learned=False,
        t_start=t_start,
    )


def _handle_unknown_skill(
    unknown_skill: str, session_id: str, sess_info: dict, t_start: float
) -> dict:
    """Build response for unknown skill."""
    from src.mcp_core.skills import list_skills

    available = ", ".join(f"/{s['name']}" for s in list_skills()) or "(belum ada skill)"
    elapsed = round(time.time() - t_start, 2)
    logger.info("[%s] Skill tidak dikenal: /%s", session_id, unknown_skill)
    return {
        "answer": f"Skill '/{unknown_skill}' tidak dikenal. Skill yang tersedia: {available}.",
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


def _build_augmented_prompt(
    system_prompt: str,
    skill_block: str,
    user_input: str,
    session_id: str,
    agent_type: str,
) -> str:
    """Build augmented system prompt with skill, preferences, RAG, projects, monologue."""
    augmented_prompt = system_prompt + skill_block

    try:
        from src.plugins.core_tools import get_preferences_block

        _pref_block = get_preferences_block()
        if _pref_block:
            augmented_prompt += f"\n\n## {_pref_block}"
    except Exception as _e:
        logger.debug("Preferences block error: %s", _e)

    try:
        from src.mcp_core.retrieval import build_references

        _ref_block = build_references(user_input)
        if _ref_block:
            augmented_prompt += f"\n\n{_ref_block}"
    except Exception as _e:
        logger.debug("RAG references error: %s", _e)

    try:
        from src.plugins.core_tools import get_projects_block

        _proj_block = get_projects_block()
        if _proj_block:
            augmented_prompt += f"\n\n## {_proj_block}"
    except Exception as _e:
        logger.debug("Projects block error: %s", _e)

    try:
        from src.core.memory.monologue import get_latest_monologue, get_role_for_agent

        latest_monologue = get_latest_monologue(session_id, agent_type)
        if latest_monologue:
            role = latest_monologue.role
            monologue_content = latest_monologue.content
            augmented_prompt += f"\n\n## Monologue ({role})\n{monologue_content}"
        else:
            role = get_role_for_agent(agent_type)
            augmented_prompt += f"\n\n## Monologue ({role})\n[No monologue yet.]"
    except Exception as _e:
        logger.debug("Monologue load error: %s", _e)

    return augmented_prompt


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
    from src.core.routing.tools import learn_from_tool_failure, log_tool_failure
    from src.plugins.core_tools import AVAILABLE_PLUGINS

    answer = None
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
                log_tool_failure(
                    t_name, str(e), agent_type, session_id, user_input[:50]
                )
            if _attempt == 0:
                swapped, replaced = [], set()
                for t_name in tool_names:
                    alt = learn_from_tool_failure(
                        t_name, agent_type, session_id, user_input
                    )
                    for a in alt or []:
                        if (
                            a in AVAILABLE_PLUGINS
                            and a not in tool_names
                            and a not in replaced
                        ):
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
                    validated_tools = [
                        t for t in validated_tools if t.name not in replaced
                    ] + swapped
                    if validated_tools:
                        continue
            raise

    if not session_nama:
        new_nama, new_context = generate_session_name_context(user_input, answer)
        if new_nama:
            update_session(
                session_id, nama=new_nama, context=new_context, agent_type=agent_type
            )
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


def route_request_inner(user_input: str, session_id: str, _depth: int = 0) -> dict:
    """Isi route_request (dipisah agar decorator metrik tidak ganggu rekursi fan-out)."""
    from src.core.auth.approval import set_current_owner_user_id, set_current_session
    from src.core.auth.auth import get_current_user_id
    from src.core.llm.llm_shortcut import llm_shortcut
    from src.core.memory.learning import process_pending_learnings
    from src.core.memory.sessions import get_or_create_session
    from src.core.routing.adaptive_router import classify_agent
    from src.core.routing.commands import handle_bantuan, handle_ringkas
    from src.core.routing.fanout import route_fanout
    from src.core.routing.intent import auto_learn_keyword, detect_actionable_intent
    from src.core.routing.skills import extract_skill_invocation, split_fanout_segments
    from src.core.routing.tools import filter_tools_by_keywords, get_quarantined_tools
    from src.core.system.rate_limiter import TokenBucket
    from src.mcp_core.registry import load_mcp_context
    from src.mcp_core.tool_validator import validate_tools_for_agent
    from src.plugins.core_tools import AVAILABLE_PLUGINS
    from src.plugins.input_guard import validate_user_input

    t_start = time.time()

    # Input sanitization & prompt injection guard
    valid, sanitized = validate_user_input(user_input)
    if not valid:
        return _handle_injection_blocked(session_id, sanitized, t_start)
    user_input = sanitized

    try:
        set_current_session(session_id)
    except Exception as _e:
        logger.debug("set_current_session error: %s", _e)

    _bucket = TokenBucket(capacity=1, refill_per_sec=0.33)
    wait = _bucket.acquire(session_id)
    if wait > 0:
        logger.info("[%s] Rate limited, menunggu %.1fs", session_id, wait)
        time.sleep(wait)

    user_id = get_current_user_id()
    set_current_owner_user_id(user_id)
    sess_info = get_or_create_session(session_id, user_id, user_id)

    # Perintah bawaan (tanpa LLM routing)
    _text = user_input.strip()
    if _text.startswith("/bantuan"):
        return handle_bantuan(session_id, sess_info, t_start)
    if _text.startswith("/ringkas"):
        return handle_ringkas(session_id, sess_info, t_start)

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
        skill_block = f"\n\n## Invoked skill: /{skill_name}\n{skill['body']}"
        logger.info("[%s] Skill invoked: /%s", session_id, skill_name)

    # Proses feedback learning secara periodik
    if hash(session_id) % 50 == 0:
        process_pending_learnings()

    agent_type = classify_agent(user_input, user_id=session_id)
    _classified_agent = agent_type

    # Session affinity
    agent_type = _apply_session_affinity(
        agent_type, user_input, session_id, sess_info, _classified_agent
    )

    system_prompt, _default_tools = load_mcp_context(
        agent_type,
        session_nama=sess_info.get("nama"),
        session_context=sess_info.get("context"),
    )
    filtered_tools = filter_tools_by_keywords(agent_type, user_input)
    validated_tools = validate_tools_for_agent(agent_type, filtered_tools)

    # Build augmented prompt
    augmented_prompt = _build_augmented_prompt(
        system_prompt, skill_block, user_input, session_id, agent_type
    )

    logger.info(
        "[%s] -> Routing ke %s | Tools: %s",
        session_id,
        agent_type.replace("_", " ").title(),
        [t.name for t in validated_tools],
    )

    # Auto-learn
    used_auto_learn = False
    if (
        agent_type == "casual_agent"
        and not validated_tools
        and detect_actionable_intent(user_input)
    ):
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
            _dropped = sorted(
                {t.name for t in validated_tools} - {t.name for t in _kept}
            )
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
