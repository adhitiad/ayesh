# Panduan Pengguna — Asisten AI Multi-Agent

Panduan pakai sehari-hari (Bahasa Indonesia). Untuk dokumentasi developer, baca `AGENTS.md`.

## Cara Akses

| Jalur | Cara |
|---|---|
| API | `POST http://localhost:8080/chat` dengan `{"message": "..."}` |
| Streaming | `POST /chat/stream` (status → hasil) atau `/chat/stream/tokens` (per token) |
| Telegram | Set `TELEGRAM_BOT_TOKEN`, jalankan `python -m src.integrations.telegram`, chat bot |
| Background | `POST /tasks` → 202, lalu `GET /tasks/{id}` untuk hasil |

Jalankan server: `python api_server.py` (butuh PostgreSQL + Redis jalan).

## Skill (perintah `/nama`)

Ketik `/nama-skill` + pesan. Contoh:

- `/koding buatkan file hello.py` — tulis/baca/jalankan kode (otomatis dites sebelum selesai)
- `/riset-web harga emas hari ini` — cari info terkini + deep-read halaman
- `/surat-resmi buatkan izin cuti 3 hari` — draf formal birokrasi
- `/company-research profil PT X` — riset perusahaan
- `/find-security-vulnerabilities-in-code audit file app.py` — audit keamanan kode
- `/firecrawl-deep-research topik Y` — laporan riset mendalam
- `/bantuan` — daftar semua skill | `/ringkas` — ringkas session ini

Tanpa `/`, sistem otomatis pilih agent (coder/admin/casual) dari kata kunci.
Follow-up tanpa kata kunci tetap di agent yang sama; kata eksplisit pindah.

## Session & Ingatan

- Tiap percakapan punya session (ID otomatis, atau kirim `session_id` sendiri).
- **Preferensi**: katakan sekali, diingat selamanya — "nama saya Budi", "saya suka python". Berlaku lintas session.
- **Proyek**: pekerjaan multi-session — "simpan proyek renovasi-dapur: renovasi total, budget 50jt", lalu "catat: keramik sudah dipilih". Lihat via `lihat_proyek`.
- Multi-user: tiap user punya API key (`POST /users {"name": "..."}`), kirim via header `X-API-Key`. Preferensi & proyek terpisah per user.

## Tugas Terjadwal & Approval

- Jadwal: `POST /jobs {"name": "...", "prompt": "...", "interval_detik": 3600}` atau `"daily_at": "07:00"` (WIB). Aktifkan scheduler: `ENABLE_SCHEDULER=1`.
- Approval: bila `REQUIRE_APPROVAL=1`, aksi berbahaya (jalankan kode, panggil MCP, timpa file) menunggu persetujuan di `GET /approvals/pending` → `POST /approvals/{id}/approve|deny`.

## Contoh Harian

```
"tolong ingat saya pakai python 3.12"          -> tersimpan permanen
"simpan proyek laporan-umk: pantau UMK mingguan" -> proyek aktif
"carikan harga emas dan buatkan ringkasannya"  -> riset + rangkum
"/koding buatkan script cek harga emas /riset-web harga emas" -> paralel + gabung
```

## File Output & Lokasi Simpan

- File lepas tanpa proyek (laporan, csv, script sekali pakai) otomatis disimpan di folder `output/` (dibuat otomatis bila belum ada).
- Untuk project/kode multi-file, Ayesh **wajib tanya dulu** mau disimpan di mana — jawab mis. `F:/bdk`, maka file ditulis tepat di sana walau folder Ayesh ada di drive lain.
- Tanya "spek laptop saya apa?" kapan saja — Ayesh tahu partisi/drive, OS, CPU, RAM (GB + keping), Python, GPU, Redis, dan PostgreSQL mesinmu.

## Batasan

- Input yang tampak seperti prompt injection ditolak (400).
- Rate limit 30 request/menit per IP.
- Semua chat + feedback tercatat di audit log anti-rusak (`GET /audit/verify`).
- Tulis ke luar folder proyek hanya ke lokasi yang sudah kamu sebut eksplisit; file sensitif (`.env`, `*.key/pem`) selalu ditolak.

## Kebutuhan Sistem

### 1. Perangkat keras
| Kebutuhan | Minimal | Disarankan | Catatan |
|---|---|---|---|
| CPU | 2 core | 4 core | Tiap panggilan MCP men-spawn proses `npx`; fan-out paralel |
| RAM | 4 GB | 8 GB | venv + PG + Redis + worker; +~1 GB per worker uvicorn tambahan |
| Disk | 3 GB | 5 GB | Mayoritas venv; data app masih kecil |
| GPU | — | — | **Tidak dibutuhkan.** Seluruh LLM via API cloud |

### 2. Perangkat lunak
- **OS:** Windows 10/11 (PowerShell 5.1) — primer. Linux (Debian/Ubuntu) didukung, langkah di bawah.
- **Python 3.11+** (teruji 3.14.5) + `pip install -r requirements.txt` (20 paket).
- **PostgreSQL 15+** lokal, database `agent` (atau sesuaikan `DATABASE_URL`).
- **Redis 7+** lokal di `6379/0` (atau sesuaikan `REDIS_URL`).
- **Node.js + npx** — wajib untuk tools web (`cari_web`, `panggil_mcp` via `mcp-remote`).
- **Internet** — wajib permanen (LLM, Tavily/Exa, MCP remote).

### 3. Instalasi cepat (disarankan)
**Windows (tanpa install Python dulu pun bisa cek):** klik-ganda `setup-fr.exe` di folder proyek (atau `setup-fr.exe --check-only` via CMD). Butuh Python terinstall agar tahap install dependensi jalan; bila belum ada, exe memberi tahu.
```bash
python setup.py
```
**Linux:** `./setup.sh` (cek apt postgres/redis/node, venv, install, buat DB+tabel).
Skrip mengecek prasyarat, install requirements, buatkan `.env` dari contoh bila belum ada, tes koneksi PG+Redis, buat tabel DB, lalu tampilkan kunci API yang masih kosong + langkah lanjut. Tanpa argumen = interaktif aman (tak pernah menimpa `.env` / menghapus DB). Opsi: `--check-only` (cek saja), `--yes` (non-interaktif).

### 4. Instalasi manual
**Windows (PowerShell):**
```powershell
python -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # lalu isi kunci API (bagian 5)
# PostgreSQL: buat database "agent" (pgAdmin / createdb -U postgres agent)
# Redis: jalankan redis-server (WSL / Docker / installer Windows)
python -c "from src.core.db.db_engine import get_engine; from src.core.db.models import Base; Base.metadata.create_all(get_engine())"
python api_server.py
```
**Linux (Debian/Ubuntu):**
```bash
sudo apt install python3.14 python3.14-venv postgresql redis-server nodejs npm
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # lalu isi kunci API
sudo -u postgres createdb agent
sudo systemctl enable --now postgresql redis-server
python -c "from src.core.db.db_engine import get_engine; from src.core.db.models import Base; Base.metadata.create_all(get_engine())"
python api_server.py
```

### 5. Kunci API (file `.env`, jangan commit)
| Key | Status | Untuk |
|---|---|---|
| `GOOGLE_API_KEY` | **Disarankan** (gratis tier) | LLM utama (`gemini-3.8-flash`) |
| `NVIDIA_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` | Alternatif | Fallback sesuai `LLM_FALLBACK_ORDER` |
| `ANTHROPIC_API_KEY` / `COHERE_API_KEY` / `DEEPSEEK_API_KEY` | Alternatif | Provider tambahan |
| `MOONSHOT_API_KEY` / `MINIMAX_API_KEY` / `OPENROUTER_API_KEY` | Alternatif | Provider tambahan |
| `XAI_API_KEY` / `ZAI_API_KEY` / `META_API_KEY` | Alternatif | Grok/GLM/Llama |
| `TAVILY_API_KEY` + `EXA_API_KEY` | Wajib bila pakai riset web | `cari_web` + fallback |
| `TELEGRAM_BOT_TOKEN` | Bila pakai bot | `python -m src.integrations.telegram` |
| `DATABASE_URL`, `REDIS_URL` | Wajib | Koneksi PG + Redis |

### 6. Konfigurasi penting (`.env`)
| Var | Default | Efek |
|---|---|---|
| `REQUIRE_API_KEY` | `1` | Tanpa header `X-API-Key` valid → 401. Buat key: `POST /users` |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8080` | Ganti host `0.0.0.0` bila perlu akses LAN |
| `REQUIRE_APPROVAL` | `0` | `1` = tool berbahaya minta approve |
| `ENABLE_SCHEDULER` | `0` | `1` = job terjadwal jalan |
| `GOOGLE_NATIVE_TOOLS` | kosong | `google_search,code_execution,url_context` |
| `PROMPT_VARIANT` | `full` | `no-sop` / `minimal` (A/B testing) |
| `TELEGRAM_ALLOWED_IDS` | kosong (=terbuka) | Batasi chat ID bila diisi |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_TEMPERATURE` | groq / llama-3.3-70b-versatile / 0.7 | Otak agen |

### 7. Batasan operasional
- **Kuota LLM adalah bottleneck**, bukan spek mesin — 429 ditangani retry + fallback, tapi tetap melambat.
- **1 worker uvicorn** = satu crash hentikan semua; tambah `--workers` bila perlu HA (+RAM per worker).
- **MCP spawn lambat**: tiap `cari_web` boot proses `npx` baru (belasan detik pertama kali).
- **Retensi**: jalankan `python -m ops.retention` berkala; `audit_log` tak pernah dihapus.
- **Backup**: `python -m ops.backup backup` sebelum upgrade/ubah DB.
