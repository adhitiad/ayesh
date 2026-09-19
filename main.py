"""Orchestrator utama sistem Multi-Agent AI — thin re-export layer.

Semua kode inti telah dipindah ke src/core/*.py.
File ini hanya melakukan import awal (Redis patch, env) dan re-export
agar import dari luar (api_server, telegram, scheduler, tests) tetap kompatibel.
"""

# ── Redis RESP2 patch — WAJIB sebelum import modul lain ──────────────
from src.core.system.redis_patch import apply_redis_patch

apply_redis_patch()

# ── Environment ──────────────────────────────────────────────────────
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# ── Re-export publik (digunakan oleh api_server, telegram, scheduler, dll.) ──
from src.core.memory.learning import learn_from_feedback  # noqa: F401, E402

# ── Wrapper route_request dengan decorator metrik ────────────────────
from src.core.observability.usage import record_usage as _record_usage  # noqa: E402
from src.core.routing.router import route_request_inner  # noqa: E402
from src.core.routing.skills import (  # noqa: E402
    extract_skill_invocation,
    split_fanout_segments,
)
from src.core.routing.tools import get_quarantined_tools  # noqa: F401, E402


@_record_usage
def route_request(user_input: str, session_id: str, _depth: int = 0) -> dict:
    """Route permintaan ke sub-agen. Return dict JSON. Metrik dicatat otomatis."""
    return route_request_inner(user_input, session_id, _depth=_depth)


# ── Aliases untuk backward-compat (test_prompt_structure.py) ────────
_extract_skill_invocation = extract_skill_invocation
_split_fanout_segments = split_fanout_segments

# ── CLI entry point ──────────────────────────────────────────────────
if __name__ == "__main__":
    from src.cli.demo import run_demo

    run_demo()
