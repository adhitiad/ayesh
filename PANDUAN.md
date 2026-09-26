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

## Login & Keamanan Akun

Akun manusia berbeda dari API key: login pakai email ATAU username + password (atau OAuth),
sesi disimpan di cookie web (`ayesh_session`), dan bisa dilindungi 2FA.

### Daftar akun
```bash
curl -X POST http://localhost:8080/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"budi@mail.com","password":"rahasia123","name":"Budi","username":"budi"}'
```
- `username` opsional (3-32 karakter: huruf kecil/angka/`_`/`.`); kosongkan → dibuat otomatis dari
  awalan email. Username unik di seluruh sistem.
- Email wajib diverifikasi dulu sebelum bisa login (`AUTH_REQUIRE_EMAIL_VERIFICATION=1`).
- Link verifikasi dikirim via SMTP. Mode dev tanpa SMTP (`AUTH_DEV_VERIFY=1`) menampilkan
  link langsung di respons — **jangan dipakai di produksi**.
- Kalau kirim email gagal, register membalas **503** (fail-closed): akun belum aktif, ulangi nanti.
- Email sudah terdaftar? Register membalas **409** dengan `hint_provider` (mis. `google`/`github`)
  — petunjuk: login lewat provider itu, atau pakai password bila `null`.

### Verifikasi email
- Buka link dari email, atau manual: `POST /auth/email/verify {"token": "..."}`.
- Belum dapat email? `POST /auth/email/verify/request {"email":"budi@mail.com"}` (kirim ulang).

### Login
```bash
curl -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"budi@mail.com","password":"rahasia123"}'
```
- Kolom `email` menerima email ATAU username; field `identifier` juga bisa dipakai
  (`{"identifier":"budi","password":"..."}`) — keduanya case-insensitive.
- Sukses → cookie `ayesh_session` (+ `ayesh_csrf`) terpasang; kirim cookie itu di request berikutnya,
  dan header `X-CSRF-Token` untuk semua aksi ubah/hapus.
- Punya 2FA? Respons berisi `challenge` → lanjut: `POST /auth/login/2fa {"challenge":"...","code":"6 digit"}`.
- Setelah login, `GET /auth/me` menampilkan `username` dan `connected_providers`
  (daftar OAuth yang sudah terhubung, mis. `["google"]`).

### Lupa password
1. `POST /auth/password/reset {"email":"budi@mail.com"}` → link reset dikirim ke email.
2. `POST /auth/password/reset/confirm {"token":"...","new_password":"kataBaru123"}`.

### Ganti password (sudah login)
`POST /auth/password/change {"current_password":"...","new_password":"..."}`.

### Aktifkan 2FA (TOTP, disarankan)
1. `POST /auth/2fa/setup` → dapat secret/QR → masukkan ke Google Authenticator/Authy/dll.
2. `POST /auth/2fa/confirm {"code":"123456"}` → dapat **10 backup code** (sekali pakai, simpan offline).
3. Login berikutnya butuh kode dari aplikasi: `POST /auth/login/2fa`.
4. Matikan: `POST /auth/2fa/disable {"password":"..."}`. Status: `GET /auth/2fa/status`.

### Login pakai Google / GitHub
`GET /auth/oauth/google` atau `GET /auth/oauth/github` → halaman provider → kembali otomatis
ke situs dengan sesi terpasang. Bila email OAuth belum terverifikasi di provider, sistem
menolak (fail-closed) — verifikasi dulu di akun Google/GitHub Anda. Satu akun bisa menghubungkan
Google **dan** GitHub sekaligus (multi-provider).

### Kelola akun (sudah login)
- Ganti nama tampilan: `PATCH /auth/me {"name":"Nama Baru"}` (email/username tidak lewat sini).
- Lihat sesi aktif: `GET /auth/sessions`; cabut sesi tertentu: `DELETE /auth/sessions/{session_id}`.
- Kelola koneksi OAuth: `GET /auth/linked-accounts`; lepas satu: `DELETE /auth/linked-accounts/{provider}`
  (provider terakhir pada akun OAuth-only tidak bisa dilepas — akun jadi tak bisa login).
- Bikin ulang backup code 2FA (10 baru, lama hangus): `POST /auth/2fa/backup/regenerate {"password":"..."}`.
- Hapus akun sendiri (permanen): `DELETE /auth/me {"password":"..."}` + `{"code":"..."}` bila 2FA aktif.

### Keluar
`POST /auth/logout` → cookie dibersihkan (aman dipanggil berulang).

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

## Model LLM Personal

Tiap user bisa pakai model LLM berbeda (groq, google, nvidia, dll) dengan API key sendiri.

### Ganti model via chat
- `/model groq:llama-3.3-70b-versatile` — ganti model permanen (disimpan ke DB)
- `/model google:gemini-2.0-flash --session` — ganti model untuk session ini saja (tidak disimpan)
- `/model` — lihat model aktif saat ini

### Kelola config via API
- `POST /users/{uid}/llm-configs` — tambah config LLM baru
- `PUT /users/{uid}/llm-configs/{id}` — update config
- `DELETE /users/{uid}/llm-configs/{id}` — hapus config
- `PUT /users/{uid}/llm-configs/{id}/fallback` — set fallback chain

### Override skill & MCP tool
User bisa nonaktifkan skill atau MCP tool tertentu:
- `PUT /users/{uid}/skill-overrides` — toggle skill on/off
- `PUT /users/{uid}/mcp-overrides` — toggle MCP tool on/off
- `PATCH /users/{uid}/skill-overrides` — bulk update array of overrides
- Default: semua skill/MCP aktif. Hanya perlu set `enabled: false` untuk nonaktifkan.

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
- **Python 3.11+** (teruji 3.14.5) + `pip install -r requirements.txt` (32 paket: 26 runtime + 6 untuk tes/office).
- **PostgreSQL 15+** lokal, database `agent` (atau sesuaikan `DATABASE_URL`).
- **Redis 7+** lokal di `6379/0` (atau sesuaikan `REDIS_URL`).
- **Node.js + npx** — wajib untuk tools web (`cari_web`, `panggil_mcp` via `mcp-remote`).
- **Internet** — wajib permanen (LLM, Tavily/Exa, MCP remote).

### 3. Instalasi cepat (disarankan)
**Windows (tanpa install Python dulu pun bisa cek):** klik-ganda `setup-fr.exe` di folder proyek (atau `setup-fr.exe --check-only` via CMD). Butuh Python terinstall agar tahap install dependensi jalan; bila belum ada, exe memberi tahu. Sumber exe: `bootstrap.py` (PyInstaller).
```bash
python bootstrap.py
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

**Menggunakan uv (disarankan, lebih cepat dari pip):**
```powershell
# Install uv (satu kali): pip install uv  atau  irm https://astral.sh/uv/install.ps1 | iex
uv sync                          # install semua deps dari uv.lock
Copy-Item .env.example .env
# ... langkah DB + Redis sama seperti di atas
uv run python api_server.py      # jalankan server
```

**Menggunakan uvx (tanpa install permanen):**
```powershell
uvx --from "ayesh[dev]" python -m pytest   # jalankan test sekali
uvx ruff check .                           # lint sekali
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
| `GROQ_API_KEY` | **Disarankan** (gratis, cepat) | LLM utama (`groq` + `LLM_MODEL`) |
| `GOOGLE_API_KEY` / `OPENAI_API_KEY` / `NVIDIA_API_KEY` | Alternatif | Fallback sesuai `LLM_FALLBACK_ORDER` |
| `ANTHROPIC_API_KEY` / `COHERE_API_KEY` / `DEEPSEEK_API_KEY` | Alternatif | Provider tambahan |
| `MOONSHOT_API_KEY` / `MINIMAX_API_KEY` / `OPENROUTER_API_KEY` | Alternatif | Provider tambahan |
| `XAI_API_KEY` / `ZAI_API_KEY` / `META_API_KEY` | Alternatif | Grok/GLM/Llama |
| `TAVILY_API_KEY` + `EXA_API_KEY` | Wajib bila pakai riset web | `cari_web` + fallback |
| `TELEGRAM_BOT_TOKEN` | Bila pakai bot | `python -m src.integrations.telegram` |
| `DATABASE_URL`, `REDIS_URL` | Wajib | Koneksi PG + Redis |
| `DB_SECRET_KEY` | Bila ingin enkripsi at-rest | Fernet key kolom sensitif DB; generate `python -m src.core.db.encryption --generate-key` |

### 6. Konfigurasi penting (`.env`)
| Var | Default | Efek |
|---|---|---|
| `REQUIRE_API_KEY` | `1` | Tanpa header `X-API-Key` valid → 401. Buat key: `POST /users` |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8080` | Ganti host `0.0.0.0` bila perlu akses LAN |
| `REQUIRE_APPROVAL` | `0` | `1` = tool berbahaya minta approve |
| `APPROVAL_TIMEOUT_S` | `600` | Kedaluwarsa approval yang belum dijawab |
| `ENABLE_SCHEDULER` | `0` | `1` = job terjadwal jalan |
| `GOOGLE_NATIVE_TOOLS` | kosong | `google_search,code_execution,url_context` |
| `PROMPT_VARIANT` | `full` | `no-sop` / `minimal` (A/B testing) |
| `TELEGRAM_ALLOWED_IDS` | kosong (=tutup semua di production) | Wajib diisi production; kosong hanya untuk dev mode (`TELEGRAM_DEV=1`) |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_TEMPERATURE` | groq / llama-3.3-70b-versatile / 0.7 | Otak agen |
| `LOG_JSON_ENABLED` / `LOG_JSON_FILE` | `1` / `logs/ayesh.jsonl` | Structured logging + request ID tracing |
| `COST_PER_1M_PROMPT` / `_COMPLETION` | kosong | Estimasi biaya USD per request (`/usage/summary`) |

### 7. Batasan operasional
- **Kuota LLM adalah bottleneck**, bukan spek mesin — 429 ditangani retry + fallback, tapi tetap melambat.
- **1 worker uvicorn** = satu crash hentikan semua; tambah `--workers` bila perlu HA (+RAM per worker).
- **MCP spawn lambat**: tiap `cari_web` boot proses `npx` baru (belasan detik pertama kali).
- **Retensi**: jalankan `python -m ops.retention` berkala; `audit_log` tak pernah dihapus.
- **Backup**: `python -m ops.backup backup` sebelum upgrade/ubah DB.
