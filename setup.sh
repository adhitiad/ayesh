#!/usr/bin/env bash
# Setup awal proyek di Linux (Debian/Ubuntu).
#   ./setup.sh              # penuh, aman (tak timpa .env / hapus DB)
#   ./setup.sh --check-only # cek saja
set -u

CHECK_ONLY=0
for arg in "$@"; do
  [ "$arg" = "--check-only" ] && CHECK_ONLY=1
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 1

ok=1
say_ok()  { echo "  [OK] $1"; }
say_bad() { echo "  [XX] $1"; ok=0; }

echo "== 1. Python & venv =="
if command -v python3 >/dev/null 2>&1; then
  PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  say_ok "python3 $PYV"
else
  say_bad "python3 tidak ada (sudo apt install python3 python3-venv)"
fi
if [ -n "${VIRTUAL_ENV:-}" ]; then say_ok "venv aktif"; else echo "  [..] venv tidak aktif (disarankan)"; fi

echo "== 2. System services =="
for svc in postgresql redis-server; do
  if dpkg -l "$svc" 2>/dev/null | grep -q "^ii"; then say_ok "$svc terinstall"; else say_bad "$svc belum ada (sudo apt install $svc)"; fi
done
for cmd in node npx; do
  if command -v "$cmd" >/dev/null 2>&1; then say_ok "$cmd ada"; else say_bad "$cmd belum ada (sudo apt install nodejs npm)"; fi
done
if command -v pg_isready >/dev/null 2>&1 && pg_isready -q 2>/dev/null; then say_ok "PostgreSQL jalan"; else say_bad "PostgreSQL tidak jalan (sudo systemctl start postgresql)"; fi
if (echo > /dev/tcp/127.0.0.1/6379) 2>/dev/null; then say_ok "Redis jalan :6379"; else say_bad "Redis tidak jalan (sudo systemctl start redis-server)"; fi

if [ "$CHECK_ONLY" = "1" ]; then echo "--check-only: berhenti."; [ "$ok" = "1" ]; exit "$([ "$ok" = "1" ] && echo 0 || echo 1)"; fi

echo "== 3. Dependensi Python =="
if [ -n "${VIRTUAL_ENV:-}" ]; then PIP="pip"; else PIP="python3 -m pip"; fi
if $PIP install -r requirements.txt; then say_ok "pip install OK"; else say_bad "pip install gagal"; exit 1; fi

echo "== 4. File .env & database =="
if [ ! -f .env ]; then
  if [ -f .env.example ]; then cp .env.example .env; say_ok ".env dibuat — ISI kunci API-nya"; else say_bad ".env.example hilang"; fi
else
  say_ok ".env sudah ada (tidak ditimpa)"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='agent'" 2>/dev/null | grep -q 1; then
  if sudo -u postgres createdb agent 2>/dev/null; then say_ok "database agent dibuat"; else say_bad "gagal buat database agent"; fi
else
  say_ok "database agent ada"
fi

echo "== 5. Tabel & skills =="
if python3 -c "from src.core.db.db_engine import get_engine; from src.core.db.models import Base; Base.metadata.create_all(get_engine())" 2>/dev/null; then
  say_ok "tabel diverifikasi (aditif)"
else
  say_bad "create_all gagal (cek DATABASE_URL di .env)"
fi
NSKILL=$(ls ayesh/skills/*.md 2>/dev/null | wc -l)
say_ok "$NSKILL skill di ayesh/skills/"

echo
if [ "$ok" = "1" ]; then echo "SIAP. Lanjut: python api_server.py"; exit 0; fi
echo "BELUM SIAP. Betulkan [XX] di atas."
exit 1
