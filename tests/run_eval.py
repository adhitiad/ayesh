"""Runner eval LLM baku. Hasil dicatat ke tests/last_eval.json.

Butuh infra jalan (PostgreSQL + Redis + NVIDIA_API_KEY).

Pakai:
  python tests/run_eval.py                # semua kasus
  python tests/run_eval.py --fast-only    # hanya kasus tanpa LLM
  python tests/run_eval.py --case E03     # satu kasus
  python tests/run_eval.py --delay 12     # jeda antar kasus LLM (detik)

Status per kasus: pass / fail / skip (skip = rate limit 429, bukan gagal).
"""

import argparse
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from main import route_request

CASES_FILE = PROJECT_ROOT / "tests" / "eval_cases.json"
RESULTS_FILE = PROJECT_ROOT / "tests" / "last_eval.json"


def _safe(text: str) -> str:
    """Cetak aman di console Windows (cp1252)."""
    try:
        text.encode("cp1252")
        return text
    except UnicodeEncodeError:
        return text.encode("ascii", "replace").decode()


def check_expect(result: dict, expect: dict) -> list[str]:
    """Return daftar kegagalan (kosong = lolos)."""
    failures = []
    if "agent_type" in expect and result.get("agent_type") != expect["agent_type"]:
        failures.append(f"agent_type={result.get('agent_type')} != {expect['agent_type']}")
    if "shortcut" in expect and result.get("shortcut") != expect["shortcut"]:
        failures.append(f"shortcut={result.get('shortcut')} != {expect['shortcut']}")
    if "tools_used" in expect and sorted(result.get("tools_used", [])) != sorted(expect["tools_used"]):
        failures.append(f"tools_used={result.get('tools_used')} != {expect['tools_used']}")
    for tool in expect.get("tools_include", []):
        if tool not in result.get("tools_used", []):
            failures.append(f"tools_used kurang '{tool}': {result.get('tools_used')}")
    if "skill_invoked" in expect and result.get("skill_invoked") != expect["skill_invoked"]:
        failures.append(f"skill_invoked={result.get('skill_invoked')} != {expect['skill_invoked']}")
    answer = (result.get("answer") or "").lower()
    for sub in expect.get("answer_contains", []):
        if sub.lower() not in answer:
            failures.append(f"answer tidak mengandung '{sub}'")
    for sub in expect.get("answer_not_contains", []):
        if sub.lower() in answer:
            failures.append(f"answer mengandung terlarang '{sub}'")
    return failures


def run_case(case: dict, delay: float, judge: bool = False) -> dict:
    run_id = uuid.uuid4().hex[:6]
    base_session = f"eval_{case['id']}_{run_id}"
    out = {
        "id": case["id"],
        "desc": case.get("desc", ""),
        "status": "pass",
        "failures": [],
        "process_times": [],
        "session_id": base_session,
    }
    try:
        result = None
        for i, turn in enumerate(case["turns"]):
            # same_session: semua turn satu session; selain itu tiap turn terisolasi
            sid = base_session if case.get("same_session") else f"{base_session}_t{i}"
            if i > 0 and delay:
                time.sleep(delay)
            result = route_request(turn, sid)
            # Normalisasi: answer harus string (LangGraph bisa kembalikan list)
            from src.core.llm.text import extract_text

            if isinstance(result.get("answer"), list):
                result["answer"] = extract_text(result["answer"])
            out["process_times"].append(result.get("process_time"))
        out["failures"] = check_expect(result or {}, case.get("expect", {}))
        out["status"] = "pass" if not out["failures"] else "fail"
        out["answer_head"] = ((result or {}).get("answer") or "")[:200]
        if judge and out["status"] != "skipped" and result is not None:
            try:
                from tests.judge import judge_answer

                last_turn = case["turns"][-1]
                out["judge"] = judge_answer(last_turn, result.get("answer") or "")
            except Exception as e:
                out["judge"] = {"score": None, "reason": f"judge error: {str(e)[:100]}"}
    except Exception as e:
        msg = str(e)
        if "429" in msg or "Too Many Requests" in msg:
            out["status"] = "skipped"
            out["failures"] = ["rate limit 429"]
        else:
            out["status"] = "fail"
            out["failures"] = [f"exception: {msg[:200]}"]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Jalankan eval LLM baku")
    parser.add_argument("--fast-only", action="store_true")
    parser.add_argument("--case", default=None)
    parser.add_argument("--delay", type=float, default=8.0)
    parser.add_argument(
        "--judge", action="store_true", help="Nilai tiap jawaban dengan LLM-as-judge (+1 LLM call/kasus)"
    )
    args = parser.parse_args()

    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
    if args.fast_only:
        cases = [c for c in cases if c.get("fast")]
    if not cases:
        print("Tidak ada kasus yang cocok.")
        return 1

    print(f"Menjalankan {len(cases)} kasus eval...")
    results = []
    for i, case in enumerate(cases):
        if i > 0 and not case.get("fast") and args.delay:
            time.sleep(args.delay)
        res = run_case(case, args.delay, judge=args.judge)
        results.append(res)
        mark = {"pass": "LOLOS", "fail": "GAGAL", "skipped": "SKIP"}[res["status"]]
        print(_safe(f"[{mark}] {res['id']}: {res['desc']}"))
        for f in res["failures"]:
            print(_safe(f"       - {f}"))

    summary = {s: sum(1 for r in results if r["status"] == s) for s in ("pass", "fail", "skipped")}
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "summary": summary,
        "cases": results,
    }
    RESULTS_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRingkasan: {summary['pass']} lolos, {summary['fail']} gagal, {summary['skipped']} skip.")
    print(f"Tercatat di: {RESULTS_FILE}")
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
