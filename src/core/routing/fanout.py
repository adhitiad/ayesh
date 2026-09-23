"""Fan-out execution for multi-skill requests — parallel branches + LLM synthesis."""

import contextvars
import time as _time
from concurrent.futures import ThreadPoolExecutor

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.fanout")


def route_fanout(user_input: str, session_id: str, segments: list) -> dict:
    """Jalankan tiap segmen skill paralel (sub-session), lalu sintesis satu jawaban."""
    from src.core.llm.factory import get_llm
    from src.core.llm.text import extract_text

    t_start = _time.time()

    def _run_branch(idx_seg):
        from main import route_request

        idx, (skill, text) = idx_seg
        try:
            return route_request(f"/{skill} {text}", f"{session_id}_fan{idx}", _depth=1)
        except Exception as e:
            return {
                "answer": f"(cabang /{skill} gagal: {str(e)[:150]})",
                "agent_type": "casual_agent",
                "skill_invoked": skill,
            }

    _ctx = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=len(segments)) as pool:
        _futures = [
            pool.submit(ctx.run, _run_branch, iseg)
            for ctx, iseg in zip([_ctx.copy() for _ in segments], enumerate(segments), strict=False)
        ]
        results = [f.result() for f in _futures]

    parts = []
    for (skill, _), r in zip(segments, results, strict=False):
        parts.append(f"### Hasil /{skill} (oleh {r.get('agent_type')}):\n{r.get('answer', '')}")
    combined = "\n\n".join(parts)

    try:
        llm = get_llm()
        prompt = (
            "Gabungkan hasil kerja paralel berikut menjadi SATU jawaban akhir yang padu, "
            "rapi, dan tidak redundan. Bahasa Indonesia.\n\n"
            f"Permintaan user: {user_input[:800]}\n\n{combined[:6000]}"
        )
        response = llm.invoke(prompt)
        answer = extract_text(response.content if hasattr(response, "content") else str(response))
    except Exception as _e:
        logger.debug("Fanout response extraction error: %s", _e)
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
        "process_time": round(_time.time() - t_start, 2),
        "fanout": [{"skill": s, "agent": r.get("agent_type")} for (s, _), r in zip(segments, results, strict=False)],
    }
