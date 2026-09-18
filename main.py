"""Orchestrator utama sistem Multi-Agent AI dengan routing pintas & tool filtering."""

import time
import threading
import json
from collections import defaultdict
from dotenv import load_dotenv

# Patch redis to force RESP2 protocol for compatibility with old Redis server
from core.redis_patch import apply_redis_patch

apply_redis_patch()

from agents.agent_executor import run_agent_executor
from mcp_core.registry import load_mcp_context
from core.logger import setup_logger
from core.adaptive_router import classify_agent
from mcp_core.tool_validator import validate_tools_for_agent
from config.routing_keywords_pg import get_routing_keywords_with_tools, add_keyword_with_tools, invalidate_routing_cache
from plugins.core_tools import AVAILABLE_PLUGINS
from agents.llm_config import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

logger = setup_logger("orchestrator")


from core.sessions import get_or_create_session, update_session, generate_session_name_context


class _TokenBucket:
    """Token bucket rate limiter per session."""

    def __init__(self, capacity: int = 1, refill_per_sec: float = 0.33):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._buckets: dict[str, float] = defaultdict(lambda: float(capacity))
        self._timestamps: dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, session_id: str) -> float:
        with self._lock:
            now = time.time()
            last = self._timestamps.get(session_id, now)
            elapsed = now - last
            tokens = min(self.capacity, self._buckets[session_id] + elapsed * self.refill_per_sec)
            if tokens >= 1.0:
                self._buckets[session_id] = tokens - 1.0
                self._timestamps[session_id] = now
                return 0.0
            wait = (1.0 - tokens) / self.refill_per_sec
            self._buckets[session_id] = 0.0
            self._timestamps[session_id] = now + wait
            return wait


_bucket = _TokenBucket(capacity=1, refill_per_sec=0.33)


def _filter_tools_by_keywords(agent_type: str, user_input: str) -> list:
    """Filter tools berdasarkan allowed_tools per-keyword dari database."""
    try:
        full_data, _ = get_routing_keywords_with_tools()
    except Exception:
        return []

    lowered = user_input.lower()
    matched_tools: set = set()

    agent_keywords = full_data.get(agent_type, {})
    for kw, kw_data in agent_keywords.items():
        if kw in lowered:
            tools_for_kw = kw_data.get("allowed_tools", [])
            matched_tools.update(tools_for_kw)

    if not matched_tools:
        # Tidak ada keyword match → shortcut (tanpa tools)
        return []

    # Map tool names ke tool objects
    tools = []
    for tool_name in matched_tools:
        if tool_name in AVAILABLE_PLUGINS:
            tools.append(AVAILABLE_PLUGINS[tool_name])
    return tools


def _detect_actionable_intent(user_input: str) -> bool:
    """Deteksi apakah input user memiliki intent actionable (butuh tool) tapi tidak ter-detect."""
    lowered = user_input.lower()
    actionable_patterns = [
        "carikan", "cari ", "carilah",
        "buatkan", "buat ", "buatlah",
        "tulis", "tuliskan",
        "harga ", "harga", "biaya", "biayanya",
        "info ", "informasi", "berita", "terbaru", "update",
        "saham", "crypto", "bitcoin", "ethereum", "emas", "dolar", "kurs",
        "cuaca", "prakiraan",
        "jadwal", "waktu",
        "definisi", "arti ", "pengertian",
        "tutorial", "cara ", "bagaimana ",
        "script", "kode", "fungsi", "program", "python", "javascript",
        "deploy", "install", "setup",
    ]
    return any(p in lowered for p in actionable_patterns)


def _auto_learn_keyword(user_input: str, session_id: str) -> tuple[str, str, list] | None:
    """Gunakan LLM untuk menentukan agent, keyword, dan tools yang tepat, lalu simpan ke DB."""
    try:
        llm = get_llm()
        from config.rules import get_agents_block

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
- "carikan harga emas" → {{"agent": "admin_agent", "keyword": "harga emas", "allowed_tools": ["cari_web"]}}
- "cek cuaca jakarta besok" → {{"agent": "admin_agent", "keyword": "cuaca jakarta", "allowed_tools": ["cari_web"]}}
- "buatkan file python hello world" → {{"agent": "coder_agent", "keyword": "buatkan file python", "allowed_tools": ["tulis_kode", "baca_file"]}}
- "apa kabar" → {{"agent": "casual_agent", "keyword": "apa kabar", "allowed_tools": []}}"""

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=user_input),
        ]
        response = llm.invoke(messages)
        _raw = response.content if hasattr(response, "content") else str(response)
        content = "\n".join(str(x) for x in _raw) if isinstance(_raw, list) else _raw
        
        # Extract JSON
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            logger.warning(f"[{session_id}] Auto-learn: JSON tidak ditemukan di response: {content}")
            return None
        
        data = json.loads(json_match.group())
        agent = data.get("agent", "").strip().lower()
        keyword = data.get("keyword", "").strip().lower()
        allowed_tools = data.get("allowed_tools", [])
        
        # Validasi
        valid_agents = {"coder_agent", "admin_agent", "casual_agent"}
        if agent not in valid_agents:
            logger.warning(f"[{session_id}] Auto-learn: Agent tidak valid: {agent}")
            return None
        if not keyword or len(keyword) < 2:
            logger.warning(f"[{session_id}] Auto-learn: Keyword terlalu pendek: {keyword}")
            return None
        
        # Normalisasi tools
        valid_tools = {"tulis_kode", "baca_file", "cari_web", "get_current_time", "minta_review", "learn_keyword"}
        allowed_tools = [t for t in allowed_tools if t in valid_tools]
        
        # Simpan ke database
        ok = add_keyword_with_tools(agent, keyword, allowed_tools)
        if ok:
            invalidate_routing_cache()
            logger.info(f"[{session_id}] Auto-learn: Berhasil simpan '{keyword}' -> {agent} (tools: {allowed_tools})")
            return agent, keyword, allowed_tools
        else:
            logger.warning(f"[{session_id}] Auto-learn: Gagal simpan ke DB")
            return None
            
    except Exception as e:
        logger.error(f"[{session_id}] Auto-learn error: {e}")
        return None


def _log_tool_failure(tool_name: str, error_message: str, agent_type: str, session_id: str, keyword: str = ""):
    """Log tool failure ke database untuk analisis learning."""
    try:
        from core.db_engine import get_engine
        from core.models import ToolFailure
        from sqlalchemy.orm import sessionmaker

        engine = get_engine()
        Session = sessionmaker(bind=engine)
        with Session() as db:
            failure = ToolFailure(
                tool_name=tool_name,
                keyword=keyword,
                error_message=str(error_message)[:500],
                agent_type=agent_type,
                session_id=session_id,
            )
            db.add(failure)
            db.commit()
            logger.info(f"[{session_id}] Tool failure logged: {tool_name} - {str(error_message)[:100]}")
    except Exception as e:
        logger.error(f"Gagal log tool failure: {e}")


def _learn_from_tool_failure(tool_name: str, agent_type: str, session_id: str, user_input: str) -> list | None:
    """Jika tool gagal > 3 kali untuk keyword yang sama, coba ganti tool alternatif."""
    try:
        from core.db_engine import get_engine
        from core.models import ToolFailure
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import func, select

        engine = get_engine()
        Session = sessionmaker(bind=engine)

        with Session() as db:
            # Hitung kegagalan tool untuk agent ini
            result = db.execute(
                select(ToolFailure.tool_name, func.count())
                .where(ToolFailure.agent_type == agent_type)
                .where(ToolFailure.tool_name == tool_name)
                .group_by(ToolFailure.tool_name)
            ).all()

            for t_name, count in result:
                if count >= 3:
                    # Tool gagal 3+ kali → cari alternatif
                    alternatives = {
                        "cari_web": ["tulis_kode"],
                        "tulis_kode": ["baca_file"],
                        "baca_file": ["tulis_kode"],
                    }
                    alt_tools = alternatives.get(tool_name, [])
                    if alt_tools:
                        logger.info(f"[{session_id}] Tool {tool_name} gagal {count}x → alternatif: {alt_tools}")
                        return alt_tools
        return None
    except Exception as e:
        logger.error(f"Gagal analisis tool failure: {e}")
        return None


def get_quarantined_tools(minutes: int = 15, threshold: int = 3) -> set:
    """Tool dengan >=threshold kegagalan dalam N menit terakhir → karantina sementara.

    Karantina kedaluwarsa otomatis seiring waktu (jendela geser), tanpa aksi manual.
    """
    try:
        from core.db_engine import get_engine
        from core.models import ToolFailure
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import func
        from datetime import datetime, timedelta

        engine = get_engine()
        Session = sessionmaker(bind=engine)
        since = datetime.utcnow() - timedelta(minutes=minutes)
        with Session() as db:
            from sqlalchemy import select
            result = db.execute(
                select(ToolFailure.tool_name, func.count())
                .where(ToolFailure.created_at >= since)
                .group_by(ToolFailure.tool_name)
                .having(func.count() >= threshold)
            ).all()
            return {r[0] for r in result}
    except Exception:
        return set()


def _learn_from_feedback(session_id: str, user_input: str, agent_type: str, rating: int, corrected_agent: str = None):
    """Proses feedback untuk belajar. Rating ≤ 2 = perlu perbaikan."""
    try:
        from core.db_engine import get_engine
        from core.models import RoutingLearning
        from sqlalchemy.orm import sessionmaker

        engine = get_engine()
        Session = sessionmaker(bind=engine)

        # 1. Routing correction: jika corrected_agent ada
        if corrected_agent and corrected_agent != agent_type:
            valid_agents = {"coder_agent", "admin_agent", "casual_agent"}
            if corrected_agent not in valid_agents:
                return

            # Extract keyword dari user input
            keyword = user_input.lower().strip()[:50]

            # Simpan keyword baru ke routing_keywords
            ok = add_keyword_with_tools(corrected_agent, keyword, [])
            if ok:
                invalidate_routing_cache()
                # Log learning
                with Session() as db:
                    learning = RoutingLearning(
                        source="feedback_correction",
                        user_input=user_input[:500],
                        old_agent=agent_type,
                        new_agent=corrected_agent,
                        keyword=keyword,
                        tools=[],
                    )
                    db.add(learning)
                    db.commit()
                logger.info(f"Feedback learn: '{keyword}' → {corrected_agent} (sebelumnya: {agent_type})")

        # 2. Low rating analysis
        if rating <= 2:
            # Log untuk analisis
            with Session() as db:
                learning = RoutingLearning(
                    source="low_rating",
                    user_input=user_input[:500],
                    old_agent=agent_type,
                    new_agent=None,
                    keyword=user_input.lower().strip()[:50],
                    tools=[],
                )
                db.add(learning)
                db.commit()
            logger.info(f"Feedback learn: Low rating ({rating}) untuk {agent_type}")

    except Exception as e:
        logger.error(f"Gagal proses feedback learning: {e}")


def _process_pending_learnings():
    """Proses learning dari feedback yang belum diproses (dipanggil secara periodik)."""
    try:
        from core.db_engine import get_engine
        from core.models import Feedback, RoutingLearning
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select

        engine = get_engine()
        Session = sessionmaker(bind=engine)

        with Session() as db:
            # Cari feedback dengan corrected_agent yang belum diproses
            feedbacks = db.execute(
                select(Feedback)
                .where(Feedback.corrected_agent.isnot(None))
                .order_by(Feedback.created_at.desc())
                .limit(10)
            ).scalars().all()

            for fb in feedbacks:
                # Cek apakah sudah diproses
                exists = db.execute(
                    select(RoutingLearning)
                    .where(RoutingLearning.source == "feedback_correction")
                    .where(RoutingLearning.user_input == (fb.comment or ""))
                ).first()

                if not exists and fb.comment:
                    _learn_from_feedback(
                        session_id=fb.session_id,
                        user_input=fb.comment,
                        agent_type=fb.agent_type,
                        rating=fb.rating,
                        corrected_agent=fb.corrected_agent,
                    )
    except Exception as e:
        logger.error(f"Gagal process pending learnings: {e}")


def _extract_skill_invocation(user_input: str) -> tuple:
    """Parse prefix /nama-skill ala Claude Code. Return (skill_name|None, sisa_input, unknown|None)."""
    text = user_input.strip()
    if not text.startswith("/"):
        return None, user_input, None
    parts = text.split(None, 1)
    name = parts[0][1:].lower()
    rest = parts[1] if len(parts) > 1 else ""
    from mcp_core.skills import load_skill
    if load_skill(name) is None:
        return None, user_input, name
    return name, rest, None


def _split_fanout_segments(user_input: str) -> list:
    """Pecah pesan multi-skill jadi [(skill, teks)]. [] bila <2 skill dikenal."""
    import re
    from mcp_core.skills import load_skill
    found = [(m.start(), m.group(1).lower()) for m in re.finditer(r"/([\w-]+)", user_input)]
    found = [(pos, name) for pos, name in found if load_skill(name) is not None]
    if len(found) < 2:
        return []
    segments = []
    for i, (pos, name) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(user_input)
        text = user_input[pos:end].strip()
        # Buang prefix /skill dari segmen, sisakan isi
        text = re.sub(r"^/[\w-]+\s*", "", text).strip()
        segments.append((name, text or "(tanpa detail tambahan)"))
    return segments


def route_fanout(user_input: str, session_id: str, segments: list) -> dict:
    """Jalankan tiap segmen skill paralel (sub-session), lalu sintesis satu jawaban."""
    import time as _time
    from concurrent.futures import ThreadPoolExecutor
    _t_start = _time.time()

    def _run_branch(idx_seg):
        idx, (skill, text) = idx_seg
        try:
            return route_request(f"/{skill} {text}", f"{session_id}_fan{idx}", _depth=1)
        except Exception as e:
            return {"answer": f"(cabang /{skill} gagal: {str(e)[:150]})",
                    "agent_type": "casual_agent", "skill_invoked": skill}

    import contextvars
    _ctx = contextvars.copy_context()
    # Tiap cabang butuh SALINAN context sendiri (satu Context tak bisa dimasuki 2 thread)
    with ThreadPoolExecutor(max_workers=len(segments)) as pool:
        _futures = [pool.submit(ctx.run, _run_branch, iseg)
                    for ctx, iseg in zip([_ctx.copy() for _ in segments], enumerate(segments))]
        results = [f.result() for f in _futures]

    parts = []
    for (skill, _), r in zip(segments, results):
        parts.append(f"### Hasil /{skill} (oleh {r.get('agent_type')}):\n{r.get('answer', '')}")
    combined = "\n\n".join(parts)

    # Sintesis satu jawaban akhir
    try:
        llm = get_llm()
        prompt = (
            "Gabungkan hasil kerja paralel berikut menjadi SATU jawaban akhir yang padu, "
            "rapi, dan tidak redundan. Bahasa Indonesia.\n\n"
            f"Permintaan user: {user_input[:800]}\n\n{combined[:6000]}"
        )
        response = llm.invoke(prompt)
        from core.text import extract_text
        answer = extract_text(response.content if hasattr(response, "content") else str(response))
    except Exception:
        answer = combined

    agents = [r.get("agent_type") for r in results if r.get("agent_type")]
    top_agent = max(set(agents), key=agents.count) if agents else "casual_agent"
    return {
        "answer": answer,
        "agent_type": top_agent,
        "tools_used": sorted({t for r in results for t in (r.get("tools_used") or [])}),
        "shortcut": False,
        "auto_learned": False,
        "session_id": session_id,
        "session_nama": None,
        "session_context": None,
        "skill_invoked": "+".join(s for s, _ in segments),
        "process_time": round(_time.time() - _t_start, 2),
        "fanout": [{"skill": s, "agent": r.get("agent_type")} for (s, _), r in zip(segments, results)],
    }


def route_request(user_input: str, session_id: str, _depth: int = 0) -> dict:
    """Route permintaan ke sub-agen. Return dict JSON. Metrik dicatat otomatis."""
    from core.usage import record_usage as _record_usage

    @_record_usage
    def _inner(user_input: str, session_id: str, _depth: int = 0) -> dict:
        return _route_request_inner(user_input, session_id, _depth=_depth)

    return _inner(user_input, session_id, _depth=_depth)


def _route_request_inner(user_input: str, session_id: str, _depth: int = 0) -> dict:
    """Isi route_request (dipisah agar decorator metrik tidak ganggu rekursi fan-out)."""
    _t_start = time.time()

    # Input sanitization & prompt injection guard
    from plugins.input_guard import validate_user_input
    valid, sanitized = validate_user_input(user_input)
    if not valid:
        logger.warning(f"[{session_id}] Prompt injection blocked: {sanitized}")
        return {
            "answer": "Input ditolak: terdeteksi pola prompt injection. Silakan ulangi dengan pertanyaan biasa.",
            "agent_type": "casual_agent",
            "tools_used": [],
            "shortcut": True,
            "auto_learned": False,
            "session_id": session_id,
            "session_nama": None,
            "session_context": None,
            "skill_invoked": None,
            "process_time": round(time.time() - _t_start, 2),
        }
    user_input = sanitized

    try:
        from core.approval import set_current_session
        set_current_session(session_id)
    except Exception:
        pass

    wait = _bucket.acquire(session_id)
    if wait > 0:
        logger.info(f"[{session_id}] Rate limited, menunggu {wait:.1f}s")
        time.sleep(wait)

    # Get or create session
    sess_info = get_or_create_session(session_id)

    # Perintah bawaan (tanpa LLM routing): /bantuan dan /ringkas
    _text = user_input.strip()
    if _text.startswith("/bantuan"):
        from config.rules import SUBAGENTS
        from mcp_core.skills import list_skills
        lines = ["Aku adalah Ayesh, agent AI yang dibuat dengan cinta.", "", "Perintah yang tersedia:", "", "Skill (ketik /nama-skill + pesan):"]
        for s in list_skills():
            lines.append(f"- /{s['name']}: {s['description']}")
        lines.append("")
        lines.append("Agent (otomatis via keyword):")
        for name, cfg in SUBAGENTS.items():
            lines.append(f"- {name}: {cfg['when_to_use']}")
        lines += [
            "",
            "Session:",
            "- /ringkas: ringkas percakapan session ini sekarang.",
            "- /bantuan: tampilkan pesan ini.",
            "",
            "Contoh:",
            "- /surat-resmi buatkan izin cuti 3 hari",
            "- /koding buatkan file hello.py",
        ]
        elapsed = round(time.time() - _t_start, 2)
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
    if _text.startswith("/ringkas"):
        from memory.memory import get_memory_for_session
        summary = get_memory_for_session(session_id).force_summarize()
        elapsed = round(time.time() - _t_start, 2)
        answer = summary if summary else "Belum cukup pesan untuk diringkas (butuh 20 pesan tersimpan)."
        logger.info(f"[{session_id}] /ringkas: {'ringkasan dibuat' if summary else 'belum cukup pesan'}")
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

    # Fan-out: pesan berisi >=2 skill dikenal → paralel + sintesis (depth-0 saja)
    if _depth == 0:
        _segments = _split_fanout_segments(user_input)
        if _segments:
            logger.info(f"[{session_id}] Fan-out: {[s for s, _ in _segments]}")
            return route_fanout(user_input, session_id, _segments)

    # Skill invocation ala Claude Code: /nama-skill <sisa pesan>
    skill_name, user_input, unknown_skill = _extract_skill_invocation(user_input)
    skill_block = ""
    if unknown_skill:
        from mcp_core.skills import list_skills
        available = ", ".join(f"/{s['name']}" for s in list_skills()) or "(belum ada skill)"
        elapsed = round(time.time() - _t_start, 2)
        logger.info(f"[{session_id}] Skill tidak dikenal: /{unknown_skill}")
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
    if skill_name:
        from mcp_core.skills import load_skill
        skill = load_skill(skill_name)
        skill_block = f"\n\n## Invoked skill: /{skill_name}\n{skill['body']}"
        logger.info(f"[{session_id}] Skill invoked: /{skill_name}")

    # Proses feedback learning secara periodik (sekali per 50 request)
    if hash(session_id) % 50 == 0:
        _process_pending_learnings()

    agent_type = classify_agent(user_input, user_id=session_id)
    _classified_agent = agent_type

    # AFINITAS SESSION: follow-up tanpa keyword match tetap di agent session
    # (router stateless; tanpa ini "tambahkan X" / "jelaskan Y" mental ke casual).
    # Keyword eksplisit tetap pindah agent seperti biasa.
    try:
        from config.rules import SUBAGENTS
        from config.routing_keywords_pg import get_routing_keywords
        _kw_dict, _ = get_routing_keywords()
        _lowered = user_input.strip().lower()
        _has_hit = any(kw in _lowered for kws in _kw_dict.values() for kw in kws)
        _prior = sess_info.get("agent_type")
        if not _has_hit and _prior in SUBAGENTS:
            agent_type = _prior
            logger.info(f"[{session_id}] Afinitas session: tetap {agent_type} (tanpa keyword match)")
    except Exception:
        pass
    try:
        update_session(session_id, agent_type=agent_type)
    except Exception:
        pass
    # Monologue susulan bila afinitas mengubah hasil router, agar bacaan
    # get_latest_monologue(session_id, agent_final) tetap ketemu tulisannya.
    if agent_type != _classified_agent:
        try:
            from core.monologue import add_monologue, get_role_for_agent
            _role = get_role_for_agent(agent_type)
            add_monologue(
                session_id, agent_type, _role,
                f"Afinitas session: '{user_input[:120]}' tetap di {agent_type} "
                f"(role: {_role}; router awal: {_classified_agent}).",
            )
        except Exception:
            pass

    system_prompt, default_tools = load_mcp_context(
        agent_type,
        session_nama=sess_info.get("nama"),
        session_context=sess_info.get("context"),
    )
    filtered_tools = _filter_tools_by_keywords(agent_type, user_input)
    validated_tools = validate_tools_for_agent(agent_type, filtered_tools)

    # Add monologue to system prompt
    try:
        from core.monologue import get_latest_monologue, get_role_for_agent
        latest_monologue = get_latest_monologue(session_id, agent_type)
        if latest_monologue:
            role = latest_monologue.role
            monologue_content = latest_monologue.content
            system_prompt += f"\n\n## Monologue ({role})\n{monologue_content}"
        else:
            role = get_role_for_agent(agent_type)
            system_prompt += f"\n\n## Monologue ({role})\n[No monologue yet.]"
    except Exception:
        pass

    augmented_prompt = system_prompt + skill_block
    # Preferensi user lintas session (murah: 1 query, kosong bila belum ada)
    try:
        from plugins.core_tools import get_preferences_block
        _pref_block = get_preferences_block()
        if _pref_block:
            augmented_prompt += f"\n\n## {_pref_block}"
    except Exception:
        pass
    # RAG ringan: referensi dokumen internal bila relevan (kosong bila tidak)
    try:
        from mcp_core.retrieval import build_references
        _ref_block = build_references(user_input)
        if _ref_block:
            augmented_prompt += f"\n\n{_ref_block}"
    except Exception:
        pass
    # Proyek aktif user (kosong bila belum ada)
    try:
        from plugins.core_tools import get_projects_block
        _proj_block = get_projects_block()
        if _proj_block:
            augmented_prompt += f"\n\n## {_proj_block}"
    except Exception:
        pass

    logger.info(
        f"[{session_id}] -> Routing ke {agent_type.replace('_', ' ').title()} | Tools: {[t.name for t in validated_tools]}"
    )

    used_auto_learn = False
    # AUTO-LEARN: Jika casual_agent tapi input terlihat actionable, belajar keyword baru
    if agent_type == "casual_agent" and not validated_tools and _detect_actionable_intent(user_input):
        logger.info(f"[{session_id}] Auto-learn: Terdeteksi intent actionable, mempelajari keyword baru...")
        learned = _auto_learn_keyword(user_input, session_id)
        if learned:
            learned_agent, learned_keyword, learned_tools = learned
            logger.info(f"[{session_id}] Auto-learn: Berhasil, menggunakan tools yang baru dipelajari...")
            validated_tools = []
            for tool_name in learned_tools:
                if tool_name in AVAILABLE_PLUGINS:
                    validated_tools.append(AVAILABLE_PLUGINS[tool_name])
            agent_type = learned_agent
            used_auto_learn = True

    # KARANTINA: buang tool yang gagal berulang 15 menit terakhir.
    # Tidak pernah kosongkan total — bila semua dikarantina, pakai 1 yg tersisa + warning.
    _quarantined = get_quarantined_tools()
    if _quarantined:
        _kept = [t for t in validated_tools if t.name not in _quarantined]
        if _kept:
            _dropped = sorted({t.name for t in validated_tools} - {t.name for t in _kept})
            logger.info(f"[{session_id}] Karantina tool gagal berulang: {_dropped}")
            validated_tools = _kept

    session_nama = sess_info.get("nama")
    session_context = sess_info.get("context")

    # SHORTCUT: Jika tidak ada tools, panggil LLM langsung tanpa LangGraph
    if not validated_tools:
        logger.info(f"[{session_id}] Shortcut: tidak ada tools, panggil LLM langsung.")
        try:
            from memory.memory import get_memory_for_session
            memory = get_memory_for_session(session_id)

            llm = get_llm()
            # Tools native Gemini (google_search/code_execution/url_context),
            # aktif hanya bila GOOGLE_NATIVE_TOOLS diisi. Server-side.
            from agents.llm_config import bind_native_tools
            llm = bind_native_tools(llm)
            messages = [SystemMessage(content=augmented_prompt)]
            messages.extend(memory.messages)
            messages.append(HumanMessage(content=user_input))

            response = llm.invoke(messages)
            try:
                from core.usage import note_usage
                note_usage(response)
            except Exception:
                pass
            from core.text import extract_text
            answer = extract_text(response.content if hasattr(response, "content") else str(response))
            elapsed = round(time.time() - _t_start, 2)

            memory.add_user_message(user_input)
            memory.add_ai_message(answer)

            # Update session nama/context dengan jawaban (generate jika belum ada)
            if not session_nama:
                new_nama, new_context = generate_session_name_context(user_input, answer)
                if new_nama:
                    update_session(session_id, nama=new_nama, context=new_context, agent_type=agent_type)
                    session_nama = new_nama
                    session_context = new_context

            logger.info(f"[{session_id}] Selesai dalam {elapsed}s")
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
            logger.error(f"[{session_id}] Shortcut LLM gagal: {e}")
            if "429" in str(e) or "Too Many Requests" in str(e):
                raise

    # FULL PATH: agent executor dengan tool calling loop + 1x auto-retry
    # memakai tool alternatif bila ada yang gagal dan punya pengganti.
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
                _log_tool_failure(t_name, str(e), agent_type, session_id, user_input[:50])
            if _attempt == 0:
                swapped, replaced = [], set()
                for t_name in tool_names:
                    alt = _learn_from_tool_failure(t_name, agent_type, session_id, user_input)
                    for a in (alt or []):
                        if a in AVAILABLE_PLUGINS and a not in tool_names and a not in replaced:
                            swapped.append(AVAILABLE_PLUGINS[a])
                            replaced.add(a)
                    if alt:
                        replaced.add(t_name)
                if swapped:
                    logger.info(f"[{session_id}] Retry dengan tool alternatif: {[t.name for t in swapped]}")
                    validated_tools = [t for t in validated_tools if t.name not in replaced] + swapped
                    if validated_tools:
                        continue
            raise

    # Update session nama/context dengan jawaban (generate jika belum ada)
    if not session_nama:
        new_nama, new_context = generate_session_name_context(user_input, answer)
        if new_nama:
            update_session(session_id, nama=new_nama, context=new_context, agent_type=agent_type)
            session_nama = new_nama
            session_context = new_context

    return {
        "answer": answer,
        "agent_type": agent_type,
        "tools_used": [t.name for t in validated_tools],
        "shortcut": False,
        "auto_learned": used_auto_learn,
        "session_id": session_id,
        "session_nama": session_nama,
        "session_context": session_context,
        "skill_invoked": skill_name,
        "process_time": round(time.time() - _t_start, 2),
    }


if __name__ == "__main__":
    import json as json_mod

    logger.info("=== Multi-Agent System | Fase 10: Smart Routing & Shortcut ===")
    logger.info("")

    logger.info("--- Tantangan 1: Coder Agent (dengan tool) ---")
    result1 = route_request(
        session_id="session_1_coder",
        user_input="Tolong buatkan sebuah file Python bernama kalkulator.py di root direktori yang berisi fungsi pertambahan sederhana. Kamu WAJIB menggunakan tool tulis_kode untuk menyimpan file tersebut secara nyata ke komputerku.",
    )
    logger.info(f"Result: {json_mod.dumps(result1, indent=2, ensure_ascii=False)}")
    logger.info("")

    logger.info("--- Tantangan 2: Admin Agent ---")
    result2 = route_request(
        session_id="session_2_admin",
        user_input="Buatkan draf surat resmi kepada karyawan tentang penyesuaian gaji UMK Subang tahun 2025. Gunakan bahasa birokrasi yang formal.",
    )
    logger.info(f"Result: {json_mod.dumps(result2, indent=2, ensure_ascii=False)}")
    logger.info("")

    logger.info("--- Tantangan 3: Casual Agent (shortcut) ---")
    result3 = route_request(
        session_id="session_3_chat",
        user_input="Halo, ada yang bisa bantu? Apa kabar hari ini?",
    )
    logger.info(f"Result: {json_mod.dumps(result3, indent=2, ensure_ascii=False)}")
    logger.info("")

    logger.info("--- Tantangan 4: Random Test ---")
    result4 = route_request(
        session_id="session_4_random",
        user_input="Siapa presiden Indonesia sekarang?",
    )
    logger.info(f"Result: {json_mod.dumps(result4, indent=2, ensure_ascii=False)}")
    logger.info("")

    logger.info("=== Selesai ===")
