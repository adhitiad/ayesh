# AGENTS.md

## Project
Multi-agent AI orchestrator (Indonesian). Identity: **Ayesh** ("Aku adalah Ayesh, agent AI yang dibuat dengan cinta" — `## Identitas` block in every prompt). Entry point: `main.py`. Three sub-agents (coder, admin, casual) route via keyword matching. Uses LangChain, NVIDIA NIM LLM, Redis memory, FAISS RAG.

## Run
- Install deps: `pip install -r requirements.txt` (venv at `venv/`)
- Copy `.env.example` → `.env`, set at least one real LLM key (default provider `groq`; value that is still `your_*_api_key_here` won't activate a provider)
- Or: `python bootstrap.py` (pengganti `setup.py` — checks Python/pip/PG/Redis, installs deps, bootstraps `.env`, creates tables; `--check-only` for checks). Windows binary: `setup-fr.exe` (PyInstaller onefile; rebuild: `pyinstaller --onefile --console --name setup-fr bootstrap.py`). Linux: `./setup.sh`.
- Run: `python main.py`
- Redis must be running locally (`redis://localhost:6379/0`) — memory layer depends on it. NOTE: local Redis is old (no RESP3) — clients must use `protocol=2` (see monkey-patch quirk below; `bootstrap.py` checks with RESP2).

## Linting
- Run `ruff check .` before committing (config in `.ruff.toml`). All 571 tests must pass: `python -m unittest discover -s tests`.
- Bandit: `python -m bandit -r src/` — must report 0 issues (false positives annotated `# nosec `, see the `_SENSITIVE_PATTERNS` block in `error_handling.py`).
- mypy: `mypy.ini` configures a lenient baseline (`ignore_missing_imports`, noise codes off) — NOT a gate: ~110 pre-existing errors (mostly `arg-type`). Do not disable semantic codes to force a pass. New code should keep types clean; shrinking the baseline incrementally is the goal.

## Architecture

### Entry Points (root)
- `main.py` — thin re-export layer (Redis patch, env load, re-exports `route_request`/`get_quarantined_tools`/`learn_from_feedback`). `__main__` calls `src.cli.demo`.
- `api_server.py` — REST API + SSE streaming (thin wrapper; all routes in `src/api/`).
- `bootstrap.py` — bootstrap (pengganti `setup.py`; checks Python/pip/PG/Redis, installs deps, creates `.env`, creates tables). Windows binary `setup-fr.exe` dibangun dari file ini.

### Core Logic (`src/core/`)

`src/core/` is organized into 9 relevance-based subfolders:

#### `src/core/routing/` — Routing & Intent
- `router.py` — main routing engine: `route_request_inner()`, session affinity, prompt building, auto-learn, quarantine, full agent executor path.
- `adaptive_router.py` — adaptive routing logic.
- `tools.py` — `filter_tools_by_keywords()`, `log_tool_failure()`, `learn_from_tool_failure()`, `get_quarantined_tools()`.
- `intent.py` — `detect_actionable_intent()`, `auto_learn_keyword()` (LLM-based keyword learning).
- `skills.py` — `extract_skill_invocation()` (parse `/nama-skill`), `split_fanout_segments()` (multi-skill split).
- `fanout.py` — `route_fanout()` — parallel multi-skill execution + LLM synthesis.
- `commands.py` — `/bantuan` and `/ringkas` slash command handlers.

#### `src/core/auth/` — Authentication & Audit
- `auth.py` — multi-user API keys (`users` table, sha256, `X-API-Key` header, `REQUIRE_API_KEY=1`). ContextVar `current_user`; prefs/proyek scoped per user (composite PK). Endpoints: `POST/GET /users`, `DELETE /users/{id}`, `POST /users/{id}/rotate` (rotasi API key; key lama tetap valid `API_KEY_ROTATION_GRACE_HOURS` jam, default 24). Kolom rotasi (`old_key_hash`/`old_prefix`/`old_key_expires_at`) dimigrasi lazy via `_ensure_rotation_columns()` (ALTER TABLE, sekali per proses) karena tabel `users` tidak dikelola Alembic.
- `approval.py` — HITL gate (aktif bila `REQUIRE_APPROVAL=1`; `job_*` sessions auto-approve). Gate: `jalankan_python` + `panggil_mcp` selalu, `tulis_kode` hanya bila overwrite. Pending: `GET /approvals/pending`, `POST /approvals/{id}/approve|deny`. Timeout `APPROVAL_TIMEOUT_S` (default 600).
- `audit.py` — audit hash-chain: `GET /audit`, `GET /audit/verify` (TZ-canonical UTC).

#### `src/core/observability/` — Logging, Metrics, Usage
- `logger.py` — standard `logging` setup with API key redaction; JSON structured logging ke `logs/ayesh.jsonl` (`LOG_JSON_ENABLED`/`LOG_JSON_FILE`, rotasi 5MB) + request/session ID tracing via ContextVar (`get/set_request_id`, `request_log_context`, `JsonFormatter`).
- `log_handler.py` — log handler utilities.
- `observability.py` — `get_metrics()`, `health_check()`.
- `prometheus_metrics.py` — registry Prometheus hand-rolled (tanpa `prometheus_client`): counter `ayesh_http_requests_total{route,method,status}`, histogram `ayesh_http_request_duration_seconds{route}`, gauge `ayesh_postgres_up`/`ayesh_redis_up`/`ayesh_last_query_ms`; render teks format 0.0.4. `MetricsMiddleware` di `middleware.py` (ditambah terakhir → paling luar, rekam 429/500). Endpoint `GET /metrics/prometheus` (`text/plain; version=0.0.4`) — `/metrics` JSON lama tetap ada.
- `analytics.py` — failure analytics (failures 7d, learnings, feedback, error rate + `suggest_actions`); `GET /analytics`.
- `usage.py` — usage tracking decorator + token via ContextVar; tabel `request_stats`; `GET /usage/summary`, `GET /usage/recent`; estimasi biaya USD (`cost_usd`) dari `pricing.py` (tabel harga model + fallback env `COST_PER_1M_*`), lazy-ALTER kolom `model`/`cost_usd` untuk instalasi lama.
- `pricing.py` — tabel harga per-1M token USD (per model) + `estimate_cost_usd()`, fallback env `COST_PER_1M_PROMPT`/`COST_PER_1M_COMPLETION`.
- `async_log_handler.py` — async queue-based log handler (non-blocking, drops records on full queue).

#### `src/core/db/` — Database
- `db.py` — centralized `connect()`.
- `db_engine.py` — engine factory, `get_engine()`.
- `models.py` — SQLAlchemy ORM models for all tables.
- `encryption.py` — at-rest Fernet encryption for sensitive DB columns via `EncryptedText` (TypeDecorator, impl TEXT → no schema migration). Active when `DB_SECRET_KEY` set; empty = OFF (plaintext, backward-compatible). Covered columns: `sessions.context`, `session_memory.content`, `monologues.content`, `pending_approvals.args`, `preferensi.value`, `scheduled_jobs.prompt`, `background_tasks.input`/`result`. Fail-closed: value that looks like a Fernet token but fails to decrypt → `RuntimeError` (wrong key/corrupt), never returned raw. Legacy plaintext passes through. `user_memory.value` excluded (uses `ilike` search); `audit_log.details` excluded (hash-chain). CLI: `python -m src.core.db.encryption --generate-key` / `--encrypt-existing`. `ops/backup.py` uses raw SQL → backups contain ciphertext (needs same `DB_SECRET_KEY` to restore meaningfully).

#### `src/core/llm/` — LLM Integration
- `llm_shortcut.py` — direct LLM call path (no tools, no LangGraph).
- `task_routing.py` — model routing per task: `classify_task()` (agent_type + keyword → label code/admin/chat/plan/summarize), `resolve_route()` baca env `MODEL_ROUTE_<TASK>=provider[:model]` (aktif bila `MODEL_ROUTING_ENABLED=1`, default OFF), `get_llm_for_task()` cache per provider:model — resolve/init gagal → fallback fail-closed `get_llm()`. Dipakai `llm_shortcut.py` + `planning_tools.py` (plan).
- `templates.py` — prompt template library ("simpan & reuse"): registry bawaan (ringkas, surat_resmi, intent, kode_review, terjemah) + kustom via `.ayesh/templates/*.md` (autoload saat import; nama file = nama template) + `render()` placeholder-safe. Admin API `GET/POST /templates`.
- `text.py` — `extract_text()` single normalizer (used by all LLM/MCP call sites).

#### `src/core/memory/` — Session & Learning
- `learning.py` — `learn_from_feedback()`, `process_pending_learnings()`.
- `monologue.py` — monologue/summary logic.
- `sessions.py` — session management helpers.

#### `src/core/scheduler/` — Scheduled Jobs & Tasks
- `scheduler.py` — scheduled jobs (`scheduled_jobs` table: interval/daily WIB); `run_due_jobs()`, background thread via `ENABLE_SCHEDULER=1`; API: `POST/GET /jobs`, `DELETE/PATCH /jobs/{id}`, `POST /jobs/{id}/run`.
- `tasks.py` — async task queue (`background_tasks` table, 4 workers); `POST /tasks` → 202, `GET /tasks/{id}` poll.

#### `src/core/system/` — System & Workspaces
- `sysinfo.py` — introspeksi mesin stdlib-only → blok `## System` di setiap system prompt.
- `workspaces.py` — `output/` + direktori pilihan user per session (`note_target_dir`).
- `error_handling.py` — `sanitize_exception()`, structured error responses.
- `redis_patch.py` — Redis `protocol=2` monkey-patch.
- `rate_limit.py` — Redis-backed rate limiter (per-scope burst + sustained).

### API Layer (`src/api/`)
- `routes_chat.py` — `POST /chat`, `POST /chat/stream`, `POST /chat/stream/tokens`.
- `routes_feedback.py` — `POST /feedback`.
- `routes_agents.py` — `POST/GET /users`, `DELETE /users/{id}`, `POST /users/{id}/rotate`, `GET /agents`.
- `routes_jobs.py` — `POST/GET /jobs`, `DELETE/PATCH /jobs/{id}`, `POST /jobs/{id}/run`.
- `routes_tasks.py` — `POST /tasks`, `GET /tasks/{id}`.
- `routes_approvals.py` — `GET /approvals/pending`, `POST /approvals/{id}/approve|deny`.
- `routes_marketplace.py` — `GET /marketplace` (auth), `POST/DELETE /marketplace/{name}[/install]` (admin).
- `routes_control.py` — control-plane tambahan: `POST/DELETE /keywords` (admin, choke-point sanitize + rollback audit), `GET /plans`, `GET /plans/{plan_id}` (owner-scoped), `DELETE /templates/{name}` (admin; bawaan 400).
- `routes_system.py` — health, metrics, analytics, usage, audit, config.
- `models.py` — Pydantic request/response models.
- `middleware.py` — rate limiting, input guard, security headers.
- `dependencies.py` — auth dependency injection.

### CLI (`src/cli/`)
- `demo.py` — standalone demo entry point (`python -m src.cli.demo`).

### Other Modules
- `src/agents/agent_executor.py` — LangGraph tool loop; `src/agents/llm_config.py` — centralized LLM, cached singleton + Gemini native tools via `GOOGLE_NATIVE_TOOLS`.
- `src/config/rules.py` — **source of truth** for agent roles, rules, tool_policy, and `SUBAGENTS` registry.
- `src/config/routing_keywords_pg.py` — PostgreSQL-backed routing keywords.
- `src/mcp_core/registry.py` — `load_mcp_context()` builds sectioned prompt + local plugin tools.
- `src/mcp_core/versioning.py` — tool versioning (`nama@vN` kompatibel). Registrasi otomatis saat `core_tools` diimport; resolusi di `filter_tools_by_keywords` (DB boleh simpan `tool@v1`); `log_tool_failure`/`learn_from_tool_failure` simpan nama basis kanonik agar karantina konsisten. Bila tool menerbitkan versi baru: naikkan nomor di `_TOOL_VERSIONS` (`core_tools.py`) — referensi tanpa suffix otomatis memakai versi tertinggi.
- `src/mcp_core/skills.py` — invokable skill loader; `/nama-skill` intercepted in `route_request()`. Multi-skill triggers parallel fan-out + LLM synthesis.
- `src/mcp_core/retrieval.py` — dependency-free RAG (token-overlap scoring over `data/*.txt` + `.ayesh/`).
- `src/mcp_core/context_loader.py` — loads `mcp_core/mcp.json`, `.ayesh/rules/*.md`, `.ayesh/skills/*.md` into context blob.
- `src/mcp_core/client.py` — MCP client (stdio/streamablehttp/SSE transport).
- `src/mcp_core/tool_validator.py` — `TOOL_CAPABILITIES` authority dict + validation.
- `src/mcp_core/tool_wrapper.py` — tool execution wrapper with sandbox.
- `src/plugins/core_tools.py` — real tool definitions: `tulis_kode`, `baca_file`, `cari_web`, `baca_url`, `jalankan_python`, `panggil_mcp`, `learn_keyword`, `get_current_time`, `minta_review`, `ingat_preferensi`/`lihat_preferensi`, `simpan_proyek`/`catat_proyek`/`lihat_proyek`, `info_sistem`, `set_target_dir`. Manual overrides untuk discovery.
- `src/plugins/planning_tools.py` — multi-step planning: `buat_plan`/`lihat_plan`/`cari_plan`, `jalankan_langkah` (sub-LLM per langkah), `tandai_selesai`/`batal_plan`. Tabel `plans` + `plan_steps` (ORM `Plan`/`PlanStep`), owner-scoped, max 20 langkah, persist lintas session.
- `src/plugins/discovery.py` — plugin discovery otomatis (scan `src/plugins/*.py`, temukan `@tool` decorated functions, build `AVAILABLE_PLUGINS`). Manual overrides di `core_tools.py` sebagai pinning/fallback. Juga memuat tool marketplace terpasang (prioritas: installed < bawaan < manual).
- `src/plugins/marketplace.py` — marketplace tool: registry `.ayesh/marketplace/index.json` (entry: name/version/source/sha256/agents), install fail-closed (sha256 pin, anti path-traversal, nama tool tidak boleh menabrak yang ada, rollback penuh bila audit/gagal di tengah), grant masuk `TOOL_CAPABILITIES` per agent, file → `.ayesh/marketplace/installed/` (gitignored) + manifest JSON untuk uninstall bersih. Admin-only di route. Contoh tool: `kalkulator_sederhana`.
- `src/plugins/input_guard.py` — EN+ID injection patterns, 400 `PROMPT_INJECTION`.
- `src/plugins/time_tool.py` — `get_current_time` tool.
- `src/memory/memory.py` — Redis-backed chat history per `session_id`.
- `src/memory/optimized_hybrid.py` — hybrid Redis+Postgres memory with summarization.
- `src/memory/summarizer.py` — conversation summarizer.
- `src/integrations/telegram.py` — bot via aiogram 3.x (`TELEGRAM_BOT_TOKEN`); run: `python -m src.integrations.telegram`.
- `src/ops/backup.py` — backup/restore JSON 14 tabel (`python -m ops.backup backup/restore`).
- `src/ops/retention.py` — data retention (`python -m ops.retention`).
- `install_agents.py` — cross-OS installer: reads `~/.agents/*.md`, applies selected as `.ayesh/skills/`.
- `manage_keywords.py` — CLI for managing routing keywords in DB.
- `.ayesh/` — prompt content bundle: `skills/` (invokable skills) + `rules/` (SOP/policy markdown).
- `data/*.txt` — RAG source documents. Re-ingest after editing.
- `tests/` — 571 tests (unittest, fast, no LLM/infra) + end-to-end eval + security regression.
- `tests/load/locustfile.py` — load test Locust: user infra (`/health`, `/metrics`, `/metrics/prometheus`) + opsional `POST /chat` bila `LOADTEST_CHAT=1`. Run: server hidup dulu, lalu `locust -f tests/load/locustfile.py --host http://localhost:8080 -u 10 -r 2 -t 60s --headless --csv=load_results`. 429 (rate limit) dihitung terpisah, bukan failure. Dependensi: `locust` di `requirements.txt`.
- **Mutation testing**: `mutmut` 2.x (di-pin `>=2.5.1,<3` di `requirements.txt` — v3 tidak jalan native di Windows, issue boxed/mutmut#397; WSL hanya fallback). Config `[tool.mutmut]` di `pyproject.toml` (default mutate `src/core/llm/task_routing.py`, runner = interpreter venv eksplisit karena `python` di PATH bisa saja alias Store/beda env). Per modul lain: `.\venv\Scripts\mutmut.exe run --paths-to-mutate src/...` (di Linux/WSL: `--runner "venv/bin/python -m pytest -x --assert=plain"`). Hasil: `mutmut results`, diff: `mutmut results <id>`, HTML: `mutmut html`. Gate CI: `mutmut jenkins` (exit≠0 bila ada survived). Cache di `.mutmut-cache` (gitignored). Baseline `task_routing.py`: 61 mutant, **55 killed (90%)**; 6 survivor tersisa = mutant setara (alias default/`or` identik perilaku, mustahil dibunuh test).
- `tests/factories.py` — factory_boy factories untuk semua model ORM (`factory build()` tanpa infra; DB-session opt-in via `tests/conftest.py` + `pytest_factoryboy.register`). Test: `tests/test_factories.py` (unittest, no-DB). Dependensi test: `factory-boy`, `pytest-factoryboy` di `requirements.txt`.

## Critical Quirks
- **Redis monkey-patch**: `main.py` patches `redis.from_url` at import time to force `protocol=2`. If you work with Redis directly, import `main` first or replicate the patch.
- **`.env` validation**: `llm_config.py` skips provider `nvidia` bila `NVIDIA_API_KEY` kosong atau sama placeholder `your_gemini_api_key_here`; `RuntimeError` ("Tidak ada provider LLM yang tersedia") hanya muncul bila tak ada provider yang bisa dipakai sama sekali.
- **Rate limit**: HTTP API rate-limited di middleware via `src/core/system/rate_limit.py` — DUA bucket terpisah per request: **per-IP** (selalu) dan **per-user** (bila API key valid, kind="user"), bucket yang lebih ketat yang berlaku; env `RATE_LIMIT_{SCOPE}_BURST/SUSTAINED` (per-IP) dan `RATE_LIMIT_{SCOPE}_USER_BURST/SUSTAINED` (per-user, default mengikuti per-IP). Blok token-bucket per-session legacy di `route_request_inner` DIHAPUS (sejak refactor `b24a7b0`, impor `src.core.system.rate_limiter` sudah tidak ada → dulu setiap panggilan chat akan 500).
- **Session affinity**: follow-up tanpa keyword match tetap di agent session (bukan fallback casual). Keyword eksplisit tetap pindah agent. `agent_type` ditulis tiap request.
- **Request ID tracing**: `generate_request_id()` reuse ContextVar bila ada. ContextVar tidak menembus threadpool (`asyncio.to_thread` di `chat_stream`), jadi `route_request_inner` seed id sendiri dan `POST /chat`/`/chat/stream` meneruskan `request_id` eksplisit agar respons & log konsisten.
- **Keyword hygiene**: kata generik (`sekarang`, `waktu`, `jam`/`tulis_kode` di coder) dihapus — terbukti hijack follow-up ke agent salah.
- **No test framework**: `tests/test_prompt_structure.py` (unittest, fast, no LLM/infra — run every prompt change: `python -m unittest discover -s tests`). `tests/run_eval.py` runs `tests/eval_cases.json` (29 cases: E01–E15 core + E16–E29 multi-turn/adversarial/chaining/fanout/planning) end-to-end (needs PG+Redis+LLM) and records to `tests/last_eval.json` with pass/fail/skip (429 → skip).
- **Metrics Prometheus**: `GET /metrics/prometheus` (teks format 0.0.4, tanpa dependensi prometheus_client) — lihat `src/core/observability/prometheus_metrics.py` + `MetricsMiddleware`. `/metrics` JSON lama tetap kompatibel.
- **Slash commands**: `/nama-skill`, `/bantuan`, `/ringkas` are intercepted in `route_request()` before routing (no LLM call for `/bantuan`).
- **Streaming**: `POST /chat/stream` (SSE: `status` → `done`/`error`, ping/15s). Stage-level, not token-level. `POST /chat/stream/tokens` streams LLM tokens (LangGraph `astream_events`).
- **Security**: `plugins/input_guard.py` (EN+ID injection patterns, 400 PROMPT_INJECTION, generic refusal — patterns only in server logs). Rate limit per IP 30 req/min (`@app.middleware`). Audit hash-chain: `core/auth/audit.py`, `GET /audit`, `GET /audit/verify` (TZ-canonical UTC). File tools jailed to project root + `output/` + session-approved dirs (via `set_target_dir` setelah user menyebut lokasi eksplisit) + sensitive blocklist (`.env`, `*.key/pem`) via `_safe_path` + component-wise symlink audit `_check_component_symlinks` (fail-closed). Web/HTTP tools (`baca_url`, `upload_file`, `download_file`, `_http_request`) anti-SSRF: DNS resolve → pin ke IP asli (connect IP, hostname hanya untuk TLS SNI), redirect ikut divalidasi, batas redirect/ukuran/timeout, blok hostname suffix `.internal`/`.local`/`.svc` + host metadata (lihat `src/plugins/web_tools.py` + `src/plugins/file_ops.py`). API key hash: salted self-describing `salt$sha256` (`_hash_key`/`_verify_hash` di `core/auth/auth_keys.py`; legacy plain SHA-256 tetap dikenali + auto-upgrade saat `verify_key`). Konfigurasi auth diekspos `effective_auth_config()` dan dicatat saat startup (`api_server.py`). Enkripsi at-rest opsional via `DB_SECRET_KEY` (lihat `src/core/db/encryption.py`). API key redaction in logs (`core/observability/logger.py`). `API_HOST`/`API_PORT` env (default 127.0.0.1:8080). `TELEGRAM_ALLOWED_IDS` optional allowlist. Retention: `python -m ops.retention` (never touches `audit_log`).
- **LLM fallback**: `LLM_FALLBACK_ORDER` env (default `nvidia,groq,google,ollama`); per-provider cache. Provider didukung: `nvidia`, `groq`, `google`, `openai`, `ollama`, `anthropic`, `cohere`, `deepseek`, `moonshot`, `minimax`, `openrouter`, `grok`/`xai`, `zai`/`glm`, `meta`, + generik OpenAI-compatible (`<NAMA>_API_KEY` + `<NAMA>_BASE_URL`, mis. `tinker`). Tanpa key → provider dilewati aman.
- **Usage tracking**: `core/observability/usage.py` decorator di `route_request` (latensi/agent/tools/sukses) + token via ContextVar; tabel `request_stats`; `GET /usage/summary`, `GET /usage/recent`.
- **Closed-loop learning**: karantina otomatis tool gagal ≥3x/15 mnt (`get_quarantined_tools`); full-path auto-retry 1x dengan tool alternatif; koreksi feedback auto-apply keyword. **Auto-learn proposal-based** (fix vuln-0005/OWASP A06): output LLM TIDAK langsung tulis `routing_keywords` — masuk `pending_approvals` (`tool='learn_keyword'`) lalu aktif setelah approve owner via `POST /approvals/{id}/approve` (`decide()` re-sanitize + apply + audit `approve_learning`); keyword harus NOVEL (tolak squatting); choke-point `sanitize_keyword_tools` membatasi `allowed_tools` ⊆ `TOOL_CAPABILITIES[agent]` (dipakai juga tool `learn_keyword`); jalur immediate router di-intersect `filter_tool_names_for_agent` (narrow-only). Alasan: LLM bukan trusted component — cegah prompt-injection → konfigurasi routing global. Sesi berjalan tetap langsung pakai hasil learn (affinity menjaga kontinuitas).
- **Prompt variants**: `PROMPT_VARIANT` env (`full`/`no-sop`/`minimal`); `tests/ab_eval.py` bandingkan skor eval antar varian → `tests/ab_results.json`.
- **Routing cache**: `get_routing_keywords_with_tools` is `lru_cache` per-process. After DB keyword changes, restart a running `api_server` (or call `invalidate_routing_cache()` in-process).

## Routing Keywords (case-insensitive)
| Trigger words | Agent |
|---|---|
| `draf`, `gaji`, `upah`, `surat`, `izin` | `admin_agent` |
| `kode`, `program`, `python`, `programing` | `coder_agent` |
| anything else | `casual_agent` |

## Per-User LLM Configuration (Junction Tables)

Tiap user bisa punya multi LLM config dengan provider/model berbeda, skill/MCP overrides, dan fallback chain.

### Database Tables
- `user_llm_configs` — LLM configs per user (provider, model, api_key, temperature, is_default, is_public, fallback_config_ids)
- `user_skill_overrides` — skill on/off per user (default: all on)
- `user_mcp_overrides` — MCP tool on/off per user (default: all on)

### Auto-Migration
- `_ensure_user_config_tables()` in `auth_keys.py` creates tables + migrates old flat columns (`llm_api_key`, `llm_model`, `llm_temperature`) from `users` table
- Uses `Base.metadata.create_all()` for new tables + SQL-level migration for old columns

### Per-User Cache
- In-process dict with 5-min TTL (`USER_CONFIG_CACHE_TTL` env)
- Invalidated on every write operation + `rotate_user_key()`
- `_cache_get`/`_cache_set` in `auth_keys.py`

### Ownership + Visibility
- `list_user_llm_configs(viewer_uid, viewer_role)` — owner sees all, admin sees all, others see only public configs
- API key masked for non-self users
- `_require_ownership()` in `routes_agents.py` — all mutation endpoints require owner/admin/self

### Graph Cache
- `agent_executor.py` — cache key includes user LLM config hash to prevent user A getting user B's LLM

### Slash Command
- `/model provider:model_name` — permanent switch (DB persist)
- `/model provider:model_name --session` — session-only (ContextVar only, carries existing API key)
- `/model` — show current active model

### Fallback Chain
- `fallback_config_ids` JSON column on `user_llm_configs`
- `get_llm_for_user()` tries primary → fallback chain → global LLM
- `PUT /users/{uid}/llm-configs/{id}/fallback` — set chain

### Skill/MCP Overrides
- `PUT /users/{uid}/skill-overrides` — toggle skill on/off
- `PUT /users/{uid}/mcp-overrides` — toggle MCP tool on/off
- `PATCH .../skill-overrides` / `PATCH .../mcp-overrides` — bulk update array
- Applied in `skills.py`, `registry.py`, `tools.py`

## Data
- `data/*.txt` — RAG source documents (e.g. `kebijakan_umk.txt`, `ai_trading_guidelines.txt`). Re-ingest after editing.
- `.ayesh/skills/*.md` — invokable skills with frontmatter (`koding`, `riset-web`, `surat-resmi`); invoked via `/nama-skill`. `.ayesh/rules/*.md` — SOP/policy markdown for RAG.
- `mcp/mcp.json` — empty `{}`. MCP server config lives here when populated.
## Configurable summarization - threshold per-session, hierarchical

## Encryption Runbook (at-rest Fernet)
- Generate key: `uv run --with python-dotenv python -m src.core.db.encryption --generate-key` → simpan ke `.env` `DB_SECRET_KEY=...`
- Encrypt existing plaintext: `$env:DB_SECRET_KEY='...'; uv run --with python-dotenv python -m src.core.db.encryption --encrypt-existing`
- Fitur OFF bila `DB_SECRET_KEY` kosong → plaintext lewat kompatibel instalasi lama.
- Kolom tercakup: `sessions.context`, `session_memory.content`, `monologues.content`, `pending_approvals.args`, `preferensi.value`, `scheduled_jobs.prompt`, `background_tasks.input`, `background_tasks.result`.
- Fail-closed: token rusak / key salah → `RuntimeError`, tidak pernah return raw.
