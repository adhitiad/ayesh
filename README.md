# Ayesh — Asisten AI Multi-Agent 🇮🇩

**Aku adalah Ayesh, agent AI yang dibuat dengan cinta.** Orkestrator multi-agent berbahasa Indonesia dengan routing cerdas (keyword + LLM fallback), memori lintas sesi (Redis + PostgreSQL), RAG dokumen internal, dan tools nyata (tulis/baca file, riset web, eksekusi kode) via MCP.

## Fitur utama

- **3 sub-agent otomatis** — `coder` (ngoding), `admin` (surat/riset), `casual` (ngobrol); pindah otomatis dari kata kunci, follow-up tetap di agent yang sama.
- **Skill `/nama`** — `/koding`, `/riset-web`, `/surat-resmi`, `/company-research`, `/bantuan`, `/ringkas`, dll. Multi-skill dalam satu pesan dikerjakan paralel lalu disintesis.
- **Ingatan permanen** — preferensi ("nama saya Budi") dan proyek multi-session tersimpan di PostgreSQL; riwayat chat di Redis + ringkasan otomatis.
- **Belajar sendiri** — keyword routing baru dipelajari dari percakapan, tool yang sering gagal dikarantina otomatis + retry dengan alternatif.
- **Multi-LLM** — `nvidia`, `groq`, `google`, `openai`, `ollama`, `anthropic`, `cohere`, `deepseek`, `moonshot`, `minimax`, `openrouter`, `grok`/`xai`, `zai`/`glm`, `meta`, + endpoint OpenAI-compatible generik. Ganti cukup via `LLM_PROVIDER` di `.env`.
- **Akses banyak jalur** — REST API (+ SSE streaming), bot Telegram, background tasks, scheduled jobs, approval manusia (HITL) untuk aksi berbahaya.
- **Aman** — input guard anti prompt-injection, file tools di-jail ke project, web tools anti-SSRF (DNS pinning + batas redirect/size), audit log hash-chain, API key per user (+ rotasi), enkripsi at-rest kolom sensitif DB (Fernet, opsional), secret redaction di log.

## Mulai cepat (5 menit)

```bash
pip install -r requirements.txt
cp .env.example .env   # lalu isi API key (mis. GROQ_API_KEY)
python bootstrap.py     # cek prasyarat + install deps + buat tabel DB
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
| `bootstrap.py` | Bootstrap (pengganti `setup.py`): cek prasyarat, install deps, buat `.env`, buat tabel |
| `src/core/routing/` | Routing engine, intent detection, skill parsing, fan-out, tool filtering, commands |
| `src/core/auth/` | Multi-user API keys, HITL approval, audit hash-chain |
| `src/core/observability/` | Logging, metrics, analytics, usage tracking |
| `src/core/db/` | Database engine, ORM models, centralized connect |
| `src/core/llm/` | LLM shortcut, text normalizer |
| `src/core/memory/` | Learning, monologue, session helpers |
| `src/core/scheduler/` | Scheduled jobs, async task queue |
| `src/core/system/` | Sysinfo, workspaces, rate limiter, error handling, Redis patch |
| `src/api/` | FastAPI routes (chat, feedback, agents, jobs, tasks, approvals, system) + models + middleware |
| `src/cli/` | CLI demo entry point (`python -m src.cli.demo`) |
| `src/agents/` | LangGraph eksekutor + LLM multi-provider config |
| `src/mcp_core/` | Registry prompt, skills, RAG, tool validation, MCP client |
| `src/memory/` | Riwayat chat hybrid Redis + Postgres + summarizer |
| `src/plugins/` | Definisi tool nyata (`tulis_kode`, `cari_web`, ...) + input guard |
| `src/integrations/` | Bot Telegram |
| `src/config/` | Rules, routing keywords (DB-backed) |
| `src/ops/` | Backup/restore, data retention |
| `.ayesh/` | Skill & SOP markdown (install via `install_agents.py`) |
| `tests/` | 454 tes (cepat) + eval end-to-end + security regression |

## Dokumentasi

- [`PANDUAN.md`](PANDUAN.md) — panduan pengguna sehari-hari.
- [`AGENTS.md`](AGENTS.md) — arsitektur & quirks untuk developer.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — cara berkontribusi, lapor bug, minta fitur.

## Tes & Linting

```bash
python -m unittest discover -s tests   # 454 tes cepat, wajib lolos tiap ubah prompt
ruff check .                            # linting (config di .ruff.toml)
python -m tests.run_eval               # end-to-end (butuh PG + Redis + LLM)
```

## Lisensi & donasi

Lihat [`CONTRIBUTING.md`](CONTRIBUTING.md) untuk donasi/sponsor. Dibuat dengan cinta di Indonesia.
