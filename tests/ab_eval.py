"""A/B testing prompt: jalankan subset eval di tiap varian, bandingkan skor.

Varian dibaca dari env PROMPT_VARIANT (full | no-sop | minimal).
Hasil ke tests/ab_results.json.

Pakai:
  python tests/ab_eval.py                          # full vs no-sop
  python tests/ab_eval.py --variants full,minimal  # pilih varian
  python tests/ab_eval.py --cases E03,E05,E07       # pilih kasus

CATATAN: LLM non-deterministik — selisih 1 kasus belum tentu signifikan.
Ulangi bila hasil mepet sebelum menyimpulkan.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_FILE = PROJECT_ROOT / "tests" / "ab_results.json"
DEFAULT_CASES = ["E03", "E04", "E05", "E07"]


def run_variant(variant: str, cases: list, delay: float) -> dict:
    env = dict(os.environ)
    env["PROMPT_VARIANT"] = variant
    # lru_cache per-proses tidak relevan (subproses baru per varian)
    cmd = [sys.executable, "tests/run_eval.py", "--delay", str(delay)]
    for c in cases:
        cmd += ["--case", c]
    # --case berulang: run_eval hanya dukung 1; jalankan per kasus
    results = []
    for c in cases:
        proc = subprocess.run(
            [sys.executable, "tests/run_eval.py", "--case", c, "--delay", str(delay)],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True,
        )
        try:
            report = json.loads((PROJECT_ROOT / "tests" / "last_eval.json").read_text(encoding="utf-8"))
            cases_out = report.get("cases", [])
            results.extend(cases_out)
        except Exception as e:
            results.append({"id": c, "status": "fail", "failures": [f"runner error: {e}", proc.stderr[-300:]]})
        time.sleep(1)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    return {"variant": variant, "passed": passed, "failed": failed,
            "skipped": skipped, "total": len(results), "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B testing prompt")
    parser.add_argument("--variants", default="full,no-sop")
    parser.add_argument("--cases", default=",".join(DEFAULT_CASES))
    parser.add_argument("--delay", type=float, default=8.0)
    args = parser.parse_args()

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    cases = [c.strip() for c in args.cases.split(",") if c.strip()]
    print(f"A/B: varian={variants} kasus={cases}")

    out = {"timestamp": datetime.now(timezone.utc).isoformat(), "variants": {}}
    for v in variants:
        print(f"\n--- varian: {v} ---")
        res = run_variant(v, cases, args.delay)
        out["variants"][v] = res
        print(f"{v}: {res['passed']}/{res['total']} lolos ({res['failed']} gagal, {res['skipped']} skip)")

    print("\n=== PERBANDINGAN ===")
    for v, r in out["variants"].items():
        print(f"{v:10} {r['passed']}/{r['total']} lolos")
    RESULTS_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Tercatat di: {RESULTS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
