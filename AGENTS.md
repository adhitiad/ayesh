# AGENTS.md

## Project
Multi-agent AI orchestrator (Indonesian). Identity: **Ayesh** ("Aku adalah Ayesh, agent AI yang dibuat dengan cinta" — `## Identitas` block in every prompt). Entry point: `main.py`. Three sub-agents (coder, admin, casual) route via keyword matching. Uses LangChain, NVIDIA NIM LLM, Redis memory, FAISS RAG.

## Run
- Install deps: `pip install -r requirements.txt` (venv at `venv/`)
- Copy `.env.example` → `.env`, set `NVIDIA_API_KEY` (must not be the placeholder string)
- Or: `python setup.py` (checks Python/pip/PG/Redis, installs, bootstraps `.env`, creates tables; `--check-only` for checks). Windows binary: `setup-fr.exe` (PyInstaller onefile; rebuild: `pyinstaller --onefile --console --name setup-fr setup.py`). Linux: `./setup.sh`.
- Run: `python main.py`
- Redis must be running locally (`redis://localhost:6379/0`) — memory layer depends on it. NOTE: local Redis is old (no RESP3) — clients must use `protocol=2` (see monkey-patch quirk below; `setup.py` checks with RESP2).

## Architecture

### Entry Points (root)
- `main.py` — thin re-export layer (Redis patch, env load, re-exports `route_request`/`get_quarantined_tools`/`learn_from_feedback`). `__main__` calls `src.cli.demo`.
- `api_server.py` — REST API + SSE streaming.
- `setup.py` — bootstrap (checks Python/pip/PG/Redis, installs deps, creates `.env`, creates tables).

### Core Logic (`src/core/`)
- `src/core/router.py` — main routing engine: `route_request_inner()`, session affinity, prompt building, auto-learn, quarantine, full agent executor path.
- `src/core/rate_limiter.py` — `TokenBucket` per-session rate limiter.
- `src/core/tools.py` — `filter_tools_by_keywords()`, `log_tool_failure()`, `learn_from_tool_failure()`, `get_quarantined_tools()`.
- `src/core/intent.py` — `detect_actionable_intent()`, `auto_learn_keyword()` (LLM-based keyword learning).
- `src/core/skills.py` — `extract_skill_invocation()` (parse `/nama-skill`), `split_fanout_segments()` (multi-skill split).
- `src/core/learning.py` — `learn_from_feedback()`, `process_pending_learnings()`.
- `src/core/fanout.py` — `route_fanout()` — parallel multi-skill execution + LLM synthesis.
- `src/core/commands.py` — `/bantuan` and `/ringkas` slash command handlers.
- `src/core/llm_shortcut.py` — direct LLM call path (no tools, no LangGraph).

### CLI (`src/cli/`)
- `src/cli/demo.py` — standalone demo entry point (`python -m src.cli.demo`).

### Existing Modules (now under `src/`)
- `src/core/text.py` — `extract_text()` single normalizer for str/list-blocks/.text objects (used by all LLM/MCP call sites).
- `src/core/db.py` — centralized `connect()` (replaces per-module psycopg2 boilerplate).
- `src/agents/agent_executor.py` — LangGraph tool loop; `src/agents/llm_config.py` — centralized LLM, cached singleton + Gemini native tools via `GOOGLE_NATIVE_TOOLS`.
- `src/config/rules.py` — **source of truth** for agent roles, rules, tool_policy, and `SUBAGENTS` registry (description + when_to_use, drives auto-learn prompt and `GET /agents`).
- `src/mcp_core/registry.py` — `load_mcp_context(agent_type, session_nama, session_context)` builds sectioned prompt (Harness/Environment/Session/Tools/Skills/SOP/Rules) + local plugin tools.
- `src/mcp_core/skills.py` — invokable skill loader (frontmatter `name`/`description`); `/nama-skill` intercepted in `route_request()`. Multi-skill in one message (≥2 known) triggers parallel fan-out + LLM synthesis (`route_fanout`, sub-sessions `{id}_fan{i}`).
- `src/mcp_core/retrieval.py` — dependency-free RAG (token-overlap scoring over `data/*.txt` + `ayesh/`); injected as `## Referensi` only when relevant, else zero tokens.
- `src/core/scheduler.py` — scheduled jobs (`scheduled_jobs` table: interval/daily WIB); `run_due_jobs()`, background thread via `ENABLE_SCHEDULER=1`; API: `POST/GET /jobs`, `DELETE/PATCH /jobs/{id}`, `POST /jobs/{id}/run`.
- `src/core/tasks.py` — async task queue (`background_tasks` table, 4 workers); `POST /tasks` → 202, `GET /tasks/{id}` poll; result JSON ≤20k chars.
- `src/core/approval.py` — HITL gate (aktif bila `REQUIRE_APPROVAL=1`; `job_*` sessions auto-approve). Gate: `jalankan_python` + `panggil_mcp` selalu, `tulis_kode` hanya bila overwrite. Pending: `GET /approvals/pending`, `POST /approvals/{id}/approve|deny`. Timeout `APPROVAL_TIMEOUT_S` (default 600).
- `src/core/auth.py` — multi-user API keys (`users` table, sha256, `X-API-Key` header, `REQUIRE_API_KEY=1` untuk wajib). ContextVar `current_user`; prefs/proyek scoped per user (composite PK). Endpoints: `POST/GET /users`, `DELETE /users/{id}`.
- `src/core/analytics.py` — failure analytics (failures 7d, learnings, feedback, error rate + `suggest_actions`); `GET /analytics`, CLI `python -m core.analytics`.
- `src/ops/backup.py` — backup/restore JSON 14 tabel (`python -m ops.backup backup/restore`).
- `PANDUAN.md` — user guide (Bahasa Indonesia).
- `src/integrations/telegram.py` — bot via aiogram 3.x (`TELEGRAM_BOT_TOKEN`); chat → session `tg_<id>`; run: `python -m src.integrations.telegram`.
- `tests/judge.py` — LLM-as-judge (skor 1-5 + alasan); opt-in `run_eval.py --judge`.
- `src/mcp_core/context_loader.py` — loads `mcp_core/mcp.json`, `ayesh/rules/*.md`, `ayesh/skills/*.md` into a combined context blob injected into system prompts.
- `ayesh/` — prompt content bundle: `skills/` (invokable skills with frontmatter: `koding`, `riset-web`, `surat-resmi` + installed (`company-research`, `find-security-vulnerabilities-in-code`, `firecrawl-deep-research`, dll.); invoked via `/nama-skill`), `rules/` (SOP/policy markdown, injected as `## SOP` text block).
- `src/plugins/core_tools.py` — real tool definitions: `tulis_kode` (write file), `baca_file` (read file), `cari_web` (Tavily MCP search, Exa fallback), `baca_url` (deep-read halaman), `jalankan_python` (exec + self-verify), `panggil_mcp` (invoker MCP generik, `filesystem` diblokir), `learn_keyword`, `get_current_time` (WIB), `minta_review` (advisor/reviewer), `ingat_preferensi`/`lihat_preferensi` (lintas session, tabel `preferensi`), `simpan_proyek`/`catat_proyek`/`lihat_proyek` (proyek multi-session, tabel `proyek`), `info_sistem` (spesifikasi mesin), `set_target_dir` (catat lokasi simpan pilihan user per session).
- `src/core/sysinfo.py` — introspeksi mesin stdlib-only (partisi, OS, CPU, RAM GB+keping, Python, GPU, Redis, PG; best-effort + timeout singkat, cache 5 mnt) → blok `## System` di setiap system prompt.
- `src/core/workspaces.py` — `output/` (default file lepas, auto-create) + direktori pilihan user per session (`note_target_dir`, dibaca `_safe_path` via `approval.current_session`).
- `install_agents.py` — cross-OS installer: reads `~/.agents/*.md` (`%userprofile%\.agents` on Windows, recursive incl. `skills/` subdir), offers picks, applies selected as `ayesh/skills/`.
- `src/memory/memory.py` — Redis-backed chat history per `session_id`.
- `src/core/logger.py` — standard `logging` setup.

## Critical Quirks
- **Redis monkey-patch**: `main.py` patches `redis.from_url` at import time to force `protocol=2`. If you work with Redis directly, import `main` first or replicate the patch.
- **`.env` validation**: `llm_config.py` raises `RuntimeError` if `NVIDIA_API_KEY` is missing or equals the placeholder `your_gemini_api_key_here`.
- **Rate limit**: `route_request()` sleeps 3s per call under a lock. Expect slow sequential runs. Rate limiter lives in `src/core/rate_limiter.py`.
- **Session affinity**: follow-up tanpa keyword match tetap di agent session (bukan fallback casual). Keyword eksplisit tetap pindah agent. `agent_type` ditulis tiap request.
- **Keyword hygiene**: kata generik (`sekarang`, `waktu`, `jam`/`tulis_kode` di coder) dihapus — terbukti hijack follow-up ke agent salah.
- **No test framework**: `tests/test_prompt_structure.py` (unittest, fast, no LLM/infra — run every prompt change: `python -m unittest discover -s tests`). `tests/run_eval.py` runs `tests/eval_cases.json` (26 cases: E01–E15 core + E16–E26 multi-turn/adversarial/chaining/fanout) end-to-end (needs PG+Redis+LLM) and records to `tests/last_eval.json` with pass/fail/skip (429 → skip).
- **Slash commands**: `/nama-skill`, `/bantuan`, `/ringkas` are intercepted in `route_request()` before routing (no LLM call for `/bantuan`).
- **Streaming**: `POST /chat/stream` (SSE: `status` → `done`/`error`, ping/15s). Stage-level, not token-level. `POST /chat/stream/tokens` streams LLM tokens (LangGraph `astream_events`).
- **Security**: `plugins/input_guard.py` (EN+ID injection patterns, 400 PROMPT_INJECTION, generic refusal — patterns only in server logs). Rate limit per IP 30 req/min (`@app.middleware`). Audit hash-chain: `core/audit.py`, `GET /audit`, `GET /audit/verify` (TZ-canonical UTC). File tools jailed to project root + `output/` + session-approved dirs (via `set_target_dir` setelah user menyebut lokasi eksplisit) + sensitive blocklist (`.env`, `*.key/pem`) via `_safe_path`. API key redaction in logs (`core/logger.py`). `API_HOST`/`API_PORT` env (default 127.0.0.1:8080). `TELEGRAM_ALLOWED_IDS` optional allowlist. Retention: `python -m ops.retention` (never touches `audit_log`).
- **LLM fallback**: `LLM_FALLBACK_ORDER` env (default `nvidia,groq,google,ollama`); per-provider cache. Provider didukung: `nvidia`, `groq`, `google`, `openai`, `ollama`, `anthropic`, `cohere`, `deepseek`, `moonshot`, `minimax`, `openrouter`, `grok`/`xai`, `zai`/`glm`, `meta`, + generik OpenAI-compatible (`<NAMA>_API_KEY` + `<NAMA>_BASE_URL`, mis. `tinker`). Tanpa key → provider dilewati aman.
- **Usage tracking**: `core/usage.py` decorator di `route_request` (latensi/agent/tools/sukses) + token via ContextVar; tabel `request_stats`; `GET /usage/summary`, `GET /usage/recent`.
- **Closed-loop learning**: karantina otomatis tool gagal ≥3x/15 mnt (`get_quarantined_tools`); full-path auto-retry 1x dengan tool alternatif; koreksi feedback auto-apply keyword.
- **Prompt variants**: `PROMPT_VARIANT` env (`full`/`no-sop`/`minimal`); `tests/ab_eval.py` bandingkan skor eval antar varian → `tests/ab_results.json`.
- **Routing cache**: `get_routing_keywords_with_tools` is `lru_cache` per-process. After DB keyword changes, restart a running `api_server` (or call `invalidate_routing_cache()` in-process).

## Routing Keywords (case-insensitive)
| Trigger words | Agent |
|---|---|
| `draf`, `gaji`, `upah`, `surat`, `izin` | `admin_agent` |
| `kode`, `program`, `python`, `programing` | `coder_agent` |
| anything else | `casual_agent` |

## Data
- `data/*.txt` — RAG source documents (e.g. `kebijakan_umk.txt`, `ai_trading_guidelines.txt`). Re-ingest after editing.
- `ayesh/skills/*.md` — invokable skills with frontmatter (`koding`, `riset-web`, `surat-resmi`); invoked via `/nama-skill`. `ayesh/rules/*.md` — SOP/policy markdown for RAG.
- `mcp/mcp.json` — empty `{}`. MCP server config lives here when populated.