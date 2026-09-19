"""Introspeksi mesin lokal untuk agen (tanpa dependensi baru).

Menyediakan: daftar partisi/drive (+ruang bebas), OS, CPU, RAM (total GB +
jumlah keping bila terdeteksi), versi Python, GPU, versi Redis, versi
PostgreSQL. Semua probe best-effort dengan timeout singkat; bila gagal,
dilaporkan sebagai tidak tersedia (bukan error).

Hasil `get_sysinfo_block()` di-cache 5 menit agar murah dipanggil tiap
request (dipakai blok `## System` di system prompt).
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

_CACHE_TTL_S = 300.0
_cache: dict = {"ts": 0.0, "block": ""}

PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"


def _gb(n_bytes: int) -> float:
    return round(n_bytes / (1024**3), 1)


def list_partitions() -> list:
    """Daftar partisi/drive: [{mount, total_gb, free_gb}]. Tak pernah raise."""
    parts = []
    try:
        if os.name == "nt":
            import string

            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if not os.path.exists(drive):
                    continue
                try:
                    u = shutil.disk_usage(drive)
                except OSError:
                    continue
                if u.total == 0:
                    continue  # drive optikal/kosong
                parts.append({"mount": drive, "total_gb": _gb(u.total), "free_gb": _gb(u.free)})
        else:
            seen = set()
            mounts = ["/"]
            try:
                with open("/proc/mounts", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        cols = line.split()
                        if len(cols) >= 2 and cols[1].startswith("/"):
                            mounts.append(cols[1])
            except OSError:
                pass
            for mp in mounts:
                if mp in seen:
                    continue
                seen.add(mp)
                try:
                    u = shutil.disk_usage(mp)
                except OSError:
                    continue
                parts.append({"mount": mp, "total_gb": _gb(u.total), "free_gb": _gb(u.free)})
    except Exception:  # noqa: S110
        pass
    return parts


def _ram_total_gb() -> float | None:
    """Total RAM (GB). Windows via ctypes, Linux via /proc/meminfo, macOS via sysctl."""
    try:
        if os.name == "nt":
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            st = _MemStatus()
            st.dwLength = ctypes.sizeof(_MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return _gb(st.ullTotalPhys)
        if sys.platform == "darwin":
            out = _safe_sysinfo_run(
                ["sysctl", "-n", "hw.memsize"],
                timeout=5,
            )
            return _gb(int(out.stdout.strip()))
        with open("/proc/meminfo", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return _gb(kb * 1024)
    except Exception:  # noqa: S110
        pass
    return None


_ALLOWED_SYSINFO_CMDS = frozenset(
    {
        "sysctl",
        "dmidecode",
        "nvidia-smi",
        "powershell",
    }
)


def _safe_sysinfo_run(args: list, **kwargs) -> subprocess.CompletedProcess:
    """Run a sysinfo subprocess with explicit shell=False + command allowlist."""
    import shutil as _shutil

    cmd_name = args[0] if args else ""
    if cmd_name not in _ALLOWED_SYSINFO_CMDS:
        raise ValueError(f"Blocked sysinfo command: {cmd_name!r}")
    if not _shutil.which(cmd_name):
        raise FileNotFoundError(f"{cmd_name} not found on PATH")
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 8)
    return subprocess.run(args, shell=False, check=False, **kwargs)


def _ram_sticks() -> int | None:
    """Jumlah keping RAM bila terdeteksi, else None."""
    try:
        if os.name == "nt":
            out = _safe_sysinfo_run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_PhysicalMemory | Measure-Object | Select-Object -ExpandProperty Count",
                ],
                timeout=8,
            )
            n = int(out.stdout.strip().split()[0])
            return n if n > 0 else None
        out = _safe_sysinfo_run(
            ["dmidecode", "-t", "memory"],
            timeout=8,
        )
        n = sum(
            1
            for line in out.stdout.splitlines()
            if line.strip().startswith("Size:") and "No Module Installed" not in line
        )
        return n or None
    except Exception:
        return None


def get_ram_info() -> dict:
    """Return {total_gb|None, sticks|None}."""
    return {"total_gb": _ram_total_gb(), "sticks": _ram_sticks()}


def get_gpu_info() -> str | None:
    """Nama GPU pertama bila ada (nvidia-smi), else None (=nothing)."""
    try:
        if not shutil.which("nvidia-smi"):
            return None
        out = _safe_sysinfo_run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            timeout=8,
        )
        for line in out.stdout.splitlines():
            name = line.strip()
            if name:
                return name
    except Exception:  # noqa: S110
        pass
    return None


def _split_hostport(netloc: str, default_port: int) -> tuple:
    host, _, port = netloc.partition(":")
    try:
        return host or "localhost", int(port) if port else default_port
    except ValueError:
        return host or "localhost", default_port


def get_redis_info() -> dict:
    """Return {ok, version|None, addr}. Probe RESP2 mentah, timeout singkat."""
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        parts = urlparse(url)
        host, port = _split_hostport(parts.netloc, 6379)
        addr = f"{host}:{port}"
        with socket.create_connection((host, port), timeout=1.5) as sock:
            sock.settimeout(1.5)
            sock.sendall(b"*1\r\n$4\r\nPING\r\n")
            if not sock.recv(64).startswith(b"+PONG"):
                return {"ok": False, "version": None, "addr": addr}
            sock.sendall(b"*2\r\n$4\r\nINFO\r\n$6\r\nserver\r\n")
            buf = b""
            while b"redis_version:" not in buf:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 8192:
                    break
            version = None
            for line in buf.decode("utf-8", "ignore").splitlines():
                if line.startswith("redis_version:"):
                    version = line.split(":", 1)[1].strip()
                    break
            return {"ok": True, "version": version, "addr": addr}
    except Exception:
        try:
            parts = urlparse(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            host, port = _split_hostport(parts.netloc, 6379)
            return {"ok": False, "version": None, "addr": f"{host}:{port}"}
        except Exception:
            return {"ok": False, "version": None, "addr": "localhost:6379"}


def get_postgres_info() -> dict:
    """Return {ok, version|None}. SELECT version() dengan timeout singkat."""
    url = os.getenv("DATABASE_URL", "")
    try:
        import psycopg2

        if not url:
            return {"ok": False, "version": None}
        conn = psycopg2.connect(url, connect_timeout=2)
        try:
            cur = conn.cursor()
            cur.execute("SELECT version();")
            row = cur.fetchone()
            ver = None
            if row and row[0]:
                toks = str(row[0]).split()
                # "PostgreSQL 15.4 ..." -> "15.4"
                ver = toks[1] if len(toks) > 1 and toks[0] == "PostgreSQL" else toks[0]
            return {"ok": True, "version": ver}
        finally:
            import contextlib

            with contextlib.suppress(Exception):
                conn.close()
    except Exception:
        return {"ok": False, "version": None}


def collect_sysinfo() -> dict:
    """Kumpulkan semua info mesin. Tak pernah raise (field gagal = None/False)."""
    ram = get_ram_info()
    redis = get_redis_info()
    pg = get_postgres_info()
    py_ver = sys.version.split()[0]
    uname = platform.uname()
    return {
        "os": f"{uname.system} {uname.release} ({uname.machine})",
        "cpu": (platform.processor() or uname.machine or "tak diketahui"),
        "cpu_count": os.cpu_count() or 0,
        "ram_gb": ram["total_gb"],
        "ram_sticks": ram["sticks"],
        "python": py_ver,
        "gpu": get_gpu_info(),
        "redis_ok": redis["ok"],
        "redis_version": redis["version"],
        "redis_addr": redis["addr"],
        "postgres_ok": pg["ok"],
        "postgres_version": pg["version"],
        "partitions": list_partitions(),
    }


def format_sysinfo_block(info: dict) -> str:
    """Format dict collect_sysinfo() jadi blok markdown `## System` (pure, testable)."""
    ram = f"{info['ram_gb']} GB" if info.get("ram_gb") else "tak diketahui"
    sticks = info.get("ram_sticks")
    ram += f" ({sticks} keping)" if sticks else (" (jml keping tak diketahui)" if info.get("ram_gb") else "")
    parts = info.get("partitions") or []
    if parts:
        plist = ", ".join(f"{p['mount']} (bebas {p['free_gb']}/{p['total_gb']} GB)" for p in parts)
        ptext = f"{len(parts)} partisi: {plist}"
    else:
        ptext = "tak terdeteksi"
    gpu = info.get("gpu") or "nothing"
    if info.get("redis_ok"):
        redis = f"Yes v{info.get('redis_version') or '?'} ({info.get('redis_addr')})"
    else:
        redis = f"No (tak jalan di {info.get('redis_addr')})"
    pg = f"Yes v{info.get('postgres_version') or '?'}" if info.get("postgres_ok") else "No (tak terhubung)"
    lines = [
        "## System",
        (
            f"- OS: {info.get('os')}; CPU: {info.get('cpu')} ({info.get('cpu_count')} core); "
            f"RAM: {ram}; Python: Yes v{info.get('python')} (bila No: install {PYTHON_DOWNLOAD_URL})"
        ),
        f"- Partisi: {ptext}",
        f"- GPU: {gpu}",
        f"- Redis: {redis}",
        f"- PostgreSQL: {pg}",
    ]
    return "\n".join(lines)


def get_sysinfo_block(force: bool = False) -> str:
    """Blok markdown siap-inject ke system prompt (cache 5 menit). Tak pernah raise."""
    global _cache
    now = time.monotonic()
    if not force and _cache["block"] and (now - _cache["ts"]) < _CACHE_TTL_S:
        return _cache["block"]
    try:
        block = format_sysinfo_block(collect_sysinfo())
    except Exception:
        block = "## System\n- Info sistem tak tersedia."
    _cache = {"ts": now, "block": block}
    return block
