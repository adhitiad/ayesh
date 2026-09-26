"""Prometheus text exposition (format 0.0.4) tanpa dependensi tambahan.

Registry in-process yang thread-safe:
- Counter   ayesh_http_requests_total{route,method,status}
- Histogram ayesh_http_request_duration_seconds{route} (bucket baku)
- Gauge     ayesh_postgres_up / ayesh_redis_up / ayesh_last_query_ms (di-srape)

Route label memakai pola route (scope["route"].path) agar cardinality rendah;
request tanpa route cocok (mis. 404) memakai label "unmatched".
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

DURATION_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

_lock = threading.Lock()
# (route, method, status) -> count
_requests: dict[tuple[str, str, str], int] = {}
# route -> {"count", "sum", "buckets": {le -> count}}
_duration: dict[str, dict] = {}
# (event, outcome) -> count — event auth/keamanan (login, 2fa, reset, oauth, dll.)
_auth_events: dict[tuple[str, str], int] = {}


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _fmt(value: float) -> str:
    if value == float("inf"):
        return "+Inf"
    if value == int(value):
        return str(int(value))
    return repr(value)


def record_request(route: str, method: str, status: int, duration_s: float) -> None:
    """Catat satu request HTTP (dipanggil dari MetricsMiddleware)."""
    method = (method or "GET").upper()
    status_label = str(status)
    route_label = route or "unmatched"
    dur = max(float(duration_s), 0.0)
    with _lock:
        key = (route_label, method, status_label)
        _requests[key] = _requests.get(key, 0) + 1
        entry = _duration.setdefault(route_label, {"count": 0, "sum": 0.0, "buckets": {}})
        entry["count"] += 1
        entry["sum"] += dur
        for le in DURATION_BUCKETS:
            if dur <= le:
                entry["buckets"][le] = entry["buckets"].get(le, 0) + 1


def record_auth_event(event: str, outcome: str) -> None:
    """Catat satu event auth/keamanan (login/2fa/reset/oauth/dll.).

    Outcome memakai label tetap (ok/fail/invalid/etc.) — tidak pernah memuat data
    sensitif, hanya status. Cardinality rendah via event ternormalisasi.
    """
    with _lock:
        key = (event or "unknown", outcome or "unknown")
        _auth_events[key] = _auth_events.get(key, 0) + 1


def _health_gauges() -> list[tuple[str, float]]:
    """Ambil gauge kesehatan sekali per scrape (fail-closed -> 0 bila gagal)."""
    try:
        from src.core.observability.observability import get_metrics

        m = get_metrics()
        return [
            ("ayesh_postgres_up", 1.0 if m.get("postgres_healthy") else 0.0),
            ("ayesh_redis_up", 1.0 if m.get("redis_healthy") else 0.0),
            ("ayesh_last_query_ms", float(m.get("last_query_ms") or 0.0)),
        ]
    except Exception:
        # Security/observability subsystem error = DOWN (0), bukan UP.
        return [
            ("ayesh_postgres_up", 0.0),
            ("ayesh_redis_up", 0.0),
            ("ayesh_last_query_ms", 0.0),
        ]


def render() -> str:
    """Render seluruh registry ke teks Prometheus exposition format 0.0.4."""
    with _lock:
        req_items = sorted(_requests.items())
        dur_items = sorted(_duration.items())
        duration = {k: {"count": v["count"], "sum": v["sum"], "buckets": dict(v["buckets"])} for k, v in dur_items}

    lines: list[str] = []

    lines.append("# HELP ayesh_http_requests_total Jumlah request HTTP per route/method/status.")
    lines.append("# TYPE ayesh_http_requests_total counter")
    for (route, method, status), count in req_items:
        labels = f'route="{_escape_label(route)}",method="{_escape_label(method)}",status="{_escape_label(status)}"'
        lines.append(f"ayesh_http_requests_total{{{labels}}} {count}")

    lines.append("# HELP ayesh_http_request_duration_seconds Durasi request HTTP dalam detik.")
    lines.append("# TYPE ayesh_http_request_duration_seconds histogram")
    for route, entry in duration.items():
        label = f'route="{_escape_label(route)}"'
        cumulative = 0
        for le in DURATION_BUCKETS:
            cumulative = entry["buckets"].get(le, 0)
            lines.append(f'ayesh_http_request_duration_seconds_bucket{{{label},le="{_fmt(le)}"}} {cumulative}')
        lines.append(f'ayesh_http_request_duration_seconds_bucket{{{label},le="+Inf"}} {entry["count"]}')
        lines.append(f"ayesh_http_request_duration_seconds_sum{{{label}}} {_fmt(entry['sum'])}")
        lines.append(f"ayesh_http_request_duration_seconds_count{{{label}}} {entry['count']}")

    lines.append("# HELP ayesh_auth_events_total Jumlah event auth/keamanan per event/outcome.")
    lines.append("# TYPE ayesh_auth_events_total counter")
    for (event, outcome), count in _auth_events.items():
        labels = f'event="{_escape_label(event)}",outcome="{_escape_label(outcome)}"'
        lines.append(f"ayesh_auth_events_total{{{labels}}} {count}")

    lines.append("# HELP ayesh_postgres_up Status kesehatan PostgreSQL (1=up, 0=down).")
    lines.append("# TYPE ayesh_postgres_up gauge")
    lines.append("# HELP ayesh_redis_up Status kesehatan Redis (1=up, 0=down).")
    lines.append("# TYPE ayesh_redis_up gauge")
    lines.append("# HELP ayesh_last_query_ms Latensi query terakhir dalam milidetik.")
    lines.append("# TYPE ayesh_last_query_ms gauge")
    for name, value in _health_gauges():
        lines.append(f"{name} {_fmt(value)}")

    return "\n".join(lines) + "\n"


def reset_for_tests() -> None:
    """Kosongkan registry (hanya untuk unit test)."""
    with _lock:
        _requests.clear()
        _duration.clear()
        _auth_events.clear()


def snapshot_counts() -> dict[tuple[str, str, str], int]:
    with _lock:
        return dict(_requests)


def iter_metric_names(lines: Iterable[str]) -> set[str]:
    names = set()
    for line in lines:
        if line.startswith("#") or not line.strip():
            continue
        name = line.split("{", 1)[0].split(" ", 1)[0]
        names.add(name)
    return names
