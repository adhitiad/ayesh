# Ayesh — Asisten AI Multi-Agent 🇮🇩

**Aku adalah Ayesh, agent AI yang dibuat dengan cinta.** Orkestrator multi-agent berbahasa Indonesia dengan routing cerdas (keyword + LLM fallback), memori lintas sesi (Redis + PostgreSQL), RAG dokumen internal, dan tools nyata (tulis/baca file, riset web, eksekusi kode) via MCP.

## Fitur utama

- **3 sub-agent otomatis** — `coder` (ngoding), `admin` (surat/riset), `casual` (ngobrol); pindah otomatis dari kata kunci, follow-up tetap di agent yang sama.
- **Skill `/nama`** — `/koding`, `/riset-web`, `/surat-resmi`, `/company-research`, `/bantuan`, `/ringkas`, dll. Multi-skill dalam satu pesan dikerjakan paralel lalu disintesis.
- **Ingatan permanen** — preferensi ("nama saya Budi") dan proyek multi-session tersimpan di PostgreSQL; riwayat chat di Redis + ringkasan otomatis.
- **Belajar sendiri** — keyword routing baru dipelajari dari percakapan, tool yang sering gagal dikarantina otomatis + retry dengan alternatif.
- **Multi-LLM** — `nvidia`, `groq`, `google`, `openai`, `ollama`, `anthropic`, `cohere`, `deepseek`, `moonshot`, `minimax`, `openrouter`, `grok`/`xai`, `zai`/`glm`, `meta`, + endpoint OpenAI-compatible generik. Ganti cukup via `LLM_PROVIDER` di `.env`.
- **Akses banyak jalur** — REST API (+ SSE streaming), bot Telegram, background tasks, scheduled jobs, approval manusia (HITL) untuk aksi berbahaya.
- **Aman** — input guard anti prompt-injection, file tools di-jail ke project, audit log hash-chain, API key per user, secret redaction di log.

## Mulai cepat (5 menit)

```bash
pip install -r requirements.txt
cp .env.example .env   # lalu isi API key (mis. GROQ_API_KEY)
python setup.py        # cek prasyarat + buat tabel DB
python api_server.py   # server di http://127.0.0.1:8080
```

Butuh PostgreSQL + Redis lokal. Detail lengkap: [`PANDUAN.md`](PANDUAN.md).

```bash
curl -X POST http://127.0.0.1:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "buatkan file hello.py"}'
```

## Struktur proyek

| Path | Isi |
| --- | --- |
| `main.py` | Thin re-export layer (Redis patch + re-exports `route_request`, `get_quarantined_tools`, `learn_from_feedback`) |
| `api_server.py` | REST API + SSE streaming |
| `setup.py` | Bootstrap: cek prasyarat, install deps, buat tabel |
| `src/core/` | **Semua logika inti**: routing, rate limiter, tool filtering, intent detection, skill parsing, learning, fan-out, commands, LLM shortcut, session, scheduler, tasks, auth, approval, audit, usage, monologue, workspaces, rate limit, db, logger, analytics, observability, error handling |
| `src/cli/` | CLI demo entry point (`python -m src.cli.demo`) |
| `src/agents/` | Eksekutor LangGraph + konfigurasi LLM multi-provider |
| `src/mcp_core/` | Registry prompt, skills, RAG, validasi tool, client |
| `src/memory/` | Riwayat chat hybrid Redis + Postgres + summarizer |
| `src/plugins/` | Definisi tool nyata (`tulis_kode`, `cari_web`, …) |
| `src/integrations/` | Bot Telegram, integrasi eksternal |
| `src/config/` | Rules, routing keywords |
| `ayesh/` | Skill & SOP markdown (di-ignore git; install via `install_agents.py`) |
| `tests/` | Tes struktur (cepat) + eval end-to-end 26 kasus |

## Dokumentasi

- [`PANDUAN.md`](PANDUAN.md) — panduan pengguna sehari-hari.
- [`AGENTS.md`](AGENTS.md) — arsitektur & quirks untuk developer.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — cara berkontribusi, lapor bug, minta fitur.

## Tes

```bash
python -m unittest discover -s tests   # cepat, wajib lolos tiap ubah prompt
python -m tests.run_eval               # end-to-end (butuh PG + Redis + LLM)
```

## Lisensi & donasi

Lihat [`CONTRIBUTING.md`](CONTRIBUTING.md) untuk donasi/sponsor. Dibuat dengan cinta di Indonesia.
