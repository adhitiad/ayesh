"""Failure analytics: olah data learnings/failures/feedback/request_stats
jadi laporan siap baca + saran perbaikan konkret.

Pakai: python -m core.analytics  |  GET /analytics
"""

import logging

logger = logging.getLogger(__name__)

TOP_N = 10


def _conn():
    from src.core.db import connect

    return connect()


def tool_failure_report(limit: int = TOP_N) -> list:
    """Tool paling sering gagal + pesan error terakhir."""
    conn = _conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT tool_name, COUNT(*), MAX(created_at), "
            "(array_agg(error_message ORDER BY created_at DESC))[1] "
            "FROM tool_failures "
            "WHERE created_at > NOW() - INTERVAL '7 days' "
            "GROUP BY tool_name ORDER BY 2 DESC LIMIT %s;",
            (limit,),
        )
        rows = cur.fetchall()
    except Exception as _e:
        logger.debug("tool_failures_7d query error: %s", _e)
        rows = []
    conn.close()
    return [
        {
            "tool": r[0],
            "failures_7d": r[1],
            "last": str(r[2]),
            "last_error": (r[3] or "")[:200],
        }
        for r in rows
    ]


def learning_report() -> dict:
    """Ringkasan routing_learnings per sumber."""
    conn = _conn()
    cur = conn.cursor()
    out = {"by_source": [], "recent_corrections": []}
    try:
        cur.execute(
            "SELECT source, COUNT(*) FROM routing_learnings GROUP BY source ORDER BY 2 DESC;"
        )
        out["by_source"] = [{"source": r[0], "count": r[1]} for r in cur.fetchall()]
        cur.execute(
            "SELECT user_input, old_agent, new_agent FROM routing_learnings "
            "WHERE source = 'feedback_correction' ORDER BY id DESC LIMIT 5;"
        )
        out["recent_corrections"] = [
            {"input": (r[0] or "")[:80], "from": r[1], "to": r[2]}
            for r in cur.fetchall()
        ]
    except Exception as _e:
        logger.debug("learning_report query error: %s", _e)
    conn.close()
    return out


def feedback_report() -> dict:
    """Rating per agent + komentar rating rendah terbaru."""
    conn = _conn()
    cur = conn.cursor()
    out = {"avg_by_agent": [], "low_recent": []}
    try:
        cur.execute(
            "SELECT agent_type, ROUND(AVG(rating), 2), COUNT(*) FROM feedback GROUP BY agent_type;"
        )
        out["avg_by_agent"] = [
            {"agent": r[0], "avg": float(r[1]), "n": r[2]} for r in cur.fetchall()
        ]
        cur.execute(
            "SELECT agent_type, rating, comment FROM feedback WHERE rating <= 2 ORDER BY id DESC LIMIT 5;"
        )
        out["low_recent"] = [
            {"agent": r[0], "rating": r[1], "comment": (r[2] or "")[:200]}
            for r in cur.fetchall()
        ]
    except Exception as _e:
        logger.debug("feedback_report query error: %s", _e)
    conn.close()
    return out


def error_rate_report(hours: int = 24) -> dict:
    """Error rate + latensi p95-ish dari request_stats."""
    conn = _conn()
    cur = conn.cursor()
    out = {
        "requests": 0,
        "errors": 0,
        "error_rate": 0.0,
        "avg_latency": 0.0,
        "slowest": [],
    }
    try:
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN success THEN 0 ELSE 1 END), AVG(latency_s)"
            " FROM request_stats WHERE ts > NOW() - (%s || ' hours')::INTERVAL;",
            (str(hours),),
        )
        n, e, avg = cur.fetchone()
        n, e = int(n or 0), int(e or 0)
        out.update(
            {
                "requests": n,
                "errors": e,
                "error_rate": round(e / n, 3) if n else 0.0,
                "avg_latency": round(float(avg or 0), 2),
            }
        )
        cur.execute(
            "SELECT session_id, agent_type, latency_s, tools FROM request_stats"
            " WHERE ts > NOW() - (%s || ' hours')::INTERVAL"
            " ORDER BY latency_s DESC LIMIT 5;",
            (str(hours),),
        )
        out["slowest"] = [
            {"session": r[0], "agent": r[1], "latency": r[2], "tools": r[3]}
            for r in cur.fetchall()
        ]
    except Exception as _e:
        logger.debug("error_rate_report query error: %s", _e)
    conn.close()
    return out


def suggest_actions(report: dict) -> list:
    """Saran konkret dari angka. Pure (testable tanpa DB)."""
    tips = []
    for t in report.get("failures", []):
        if t["failures_7d"] >= 5:
            tips.append(
                f"Tool '{t['tool']}' gagal {t['failures_7d']}x/7 hari — pertimbangkan karantina permanen/patch: {t['last_error'][:100]}"
            )
    for a in report.get("feedback", {}).get("avg_by_agent", []):
        if a["n"] >= 3 and a["avg"] < 3.0:
            tips.append(
                f"Rating {a['agent']} rendah ({a['avg']}, n={a['n']}) — cek komentar low_recent + eval ulang."
            )
    er = report.get("errors", {})
    if er.get("requests", 0) >= 10 and er.get("error_rate", 0) > 0.2:
        tips.append(
            f"Error rate {er['error_rate'] * 100:.0f}%/24 jam — cek provider LLM & MCP."
        )
    if not tips:
        tips.append("Tidak ada anomali: failures rendah, rating baik, error rate aman.")
    return tips


def generate_report() -> dict:
    """Satu laporan lengkap."""
    failures = tool_failure_report()
    learnings = learning_report()
    feedback = feedback_report()
    errors = error_rate_report()
    report = {
        "failures": failures,
        "learnings": learnings,
        "feedback": feedback,
        "errors": errors,
    }
    report["suggestions"] = suggest_actions(report)
    return report


if __name__ == "__main__":
    rep = generate_report()
    print("=== FAILURE ANALYTICS (7d failures / 24h errors) ===")
    print(
        f"Requests 24h: {rep['errors']['requests']} | errors: {rep['errors']['errors']} | avg latency: {rep['errors']['avg_latency']}s"
    )
    print("\n-- Top failing tools --")
    for t in rep["failures"] or ["(tidak ada failures 7 hari)"]:
        print(
            f"  {t}"
            if isinstance(t, str)
            else f"  {t['tool']}: {t['failures_7d']}x | {t['last_error'][:100]}"
        )
    print(f"\n-- Learnings --\n  {rep['learnings']['by_source']}")
    print(f"\n-- Feedback --\n  {rep['feedback']['avg_by_agent']}")
    print("\n-- Saran --")
    for s in rep["suggestions"]:
        print(f"  - {s}")
