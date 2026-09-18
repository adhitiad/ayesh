#!/usr/bin/env python3
"""Setup awal proyek: cek prasyarat, install dep, bootstrap .env, init DB.

Pakai (dari root proyek):
  python setup.py                 # penuh, aman (tak timpa .env / hapus DB)
  python setup.py --check-only    # cek saja, tanpa install/ubah apa pun
  python setup.py --yes           # non-interaktif (untuk skrip/CI)

Keluar 0 bila siap jalan, 1 bila ada yang harus dibetulkan manual.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    # PyInstaller onefile: __file__ menunjuk ke temp _MEI; root = folder exe.
    ROOT = Path(sys.executable).resolve().parent
MIN_PYTHON = (3, 11)


def log(ok: bool, msg: str) -> bool:
    print(("  [OK] " if ok else "  [XX] ") + msg)
    return ok


def _host_python() -> str | None:
    """Interpreter untuk pip install. Exe frozen tak punya pip sendiri."""
    import shutil
    if not getattr(sys, "frozen", False):
        return sys.executable
    for cmd in ("python", "python3", "py"):
        path = shutil.which(cmd)
        if not path:
            continue
        # which bisa kena stub Microsoft Store — buktikan bisa jalan
        try:
            args = [path, "--version"] if cmd != "py" else [path, "-3", "--version"]
            r = subprocess.run(args, capture_output=True, timeout=15)
            if r.returncode == 0:
                return path
        except Exception:
            continue
    return None


def load_env_file(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("\"'")
    return env


def main() -> int:
    ap = argparse.ArgumentParser(description="Setup awal proyek")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if Path.cwd().resolve() != ROOT:
        print(f"Jalankan dari root proyek: {ROOT}")
        return 1

    ok_all = True
    print("== 1. Python & venv ==")
    ok_all &= log(sys.version_info >= MIN_PYTHON,
                   f"Python {sys.version.split()[0]} (butuh >= 3.11)")
    in_venv = sys.prefix != sys.base_prefix
    log(in_venv, "venv aktif" if in_venv else "venv TIDAK aktif (disarankan: python -m venv venv)")
    if not (args.check_only or args.yes) and not in_venv:
        try:
            input("Lanjut tanpa venv? [Enter lanjut / Ctrl+C batal] ")
        except KeyboardInterrupt:
            print("\nBatal.")
            return 1

    print("== 2. Dependensi ==")
    if args.check_only:
        req = ROOT / "requirements.txt"
        ok_all &= log(req.exists(), "requirements.txt ada")
    else:
        _py = _host_python()
        if not _py:
            ok_all &= log(False, "Python tak ditemukan (exe butuh Python terinstall untuk pip). "
                                 "Install Python 3.11+, lalu: pip install -r requirements.txt")
            return 1
        r = subprocess.run([_py, "-m", "pip", "install", "-r", "requirements.txt"],
                           cwd=ROOT, capture_output=True, text=True)
        ok_all &= log(r.returncode == 0, "pip install -r requirements.txt")
        if r.returncode != 0:
            print(r.stderr[-1500:])
            return 1

    print("== 3. File .env ==")
    env_path = ROOT / ".env"
    if not env_path.exists():
        example = ROOT / ".env.example"
        if example.exists():
            env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            ok_all &= log(True, ".env dibuat dari .env.example — ISI kunci API-nya")
        else:
            ok_all &= log(False, ".env maupun .env.example tidak ada")
    else:
        log(True, ".env sudah ada (tidak ditimpa)")

    env = load_env_file(env_path)
    for k in ("DATABASE_URL", "REDIS_URL"):
        ok_all &= log(bool(env.get(k)), f"{k} terisi")
    has_llm = any(env.get(k) and "your_" not in env.get(k, "") and "___" not in env.get(k, "")
                  for k in ("GOOGLE_API_KEY", "NVIDIA_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"))
    ok_all &= log(has_llm, "minimal 1 LLM API key terisi")

    print("== 4. PostgreSQL & Redis ==")
    try:
        sys.path.insert(0, str(ROOT))
        import psycopg2
        conn = psycopg2.connect(env.get("DATABASE_URL", ""), connect_timeout=5)
        conn.close()
        ok_all &= log(True, "PostgreSQL terhubung")
    except Exception as e:
        ok_all &= log(False, f"PostgreSQL gagal: {str(e)[:120]}")

    try:
        import redis
        # protocol=2: server Redis lokal tua tak dukung RESP3 (alasan monkey-patch di main.py)
        r = redis.from_url(env.get("REDIS_URL", "redis://localhost:6379/0"),
                           socket_connect_timeout=3, socket_timeout=3, protocol=2)
        r.ping()
        ok_all &= log(True, "Redis terhubung (RESP2)")
    except Exception as e:
        ok_all &= log(False, f"Redis gagal: {str(e)[:120]}")

    if args.check_only:
        print("\n--check-only: berhenti di sini (tanpa ubah DB)--")
        return 0 if ok_all else 1

    print("== 5. Tabel database ==")
    try:
        from core.models import Base
        # buat engine dari DATABASE_URL .env (bukan env proses, agar setup deterministik)
        from sqlalchemy import create_engine as _ce
        eng = _ce(env.get("DATABASE_URL", ""), pool_pre_ping=True)
        Base.metadata.create_all(eng)
        ok_all &= log(True, "tabel dibuat/diverifikasi (create_all, aditif)")
    except Exception as e:
        ok_all &= log(False, f"create_all gagal: {str(e)[:150]}")

    print("== 6. Skills ==")
    skills = list((ROOT / "ayesh" / "skills").glob("*.md")) if (ROOT / "ayesh" / "skills").exists() else []
    log(bool(skills), f"{len(skills)} skill di ayesh/skills/"
        + ("" if skills else " — isi via: python install_agents.py"))
    if not skills:
        print("     (boleh kosong; sistem tetap jalan dengan 0 skill invokable)")

    print()
    if ok_all:
        print("SIAP. Lanjut: python api_server.py  (lalu baca PANDUAN.md)")
        return 0
    print("BELUM SIAP. Betulkan item [XX] di atas, lalu ulangi.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
