# AGENTS.md

## Project
Multi-agent AI orchestrator (Indonesian). Entry point: `main.py`. Three sub-agents (coder, admin, casual) route via keyword matching. Uses LangChain, NVIDIA NIM LLM, Redis memory, FAISS RAG.

## Run
- Install deps: `pip install -r requirements.txt` (venv at `venv/`)
- Copy `.env.example` → `.env`, set `NVIDIA_API_KEY` (must not be the placeholder string)
- Run: `python main.py`
- Redis must be running locally (`redis://localhost:6379/0`) — memory layer depends on it

## Architecture
- `main.py` — orchestrator. Keyword router at line 52-60. Every `route_request()` call holds `api_lock` and sleeps 3s (deliberate rate limit).
- `agents/` — `coder_agent.py`, `admin_agent.py`, `casual_agent.py`. Each builds its own LLM chain with tool binding + Redis memory + RAG context.
- `agents/agent.py`, `agents/env.py` — placeholder RL framework (not yet implemented).
- `agents/llm_config.py` — centralized LLM setup. Uses `ChatNVIDIA` (NVIDIA NIM). Model defaults to `moonshotai/kimi-k3`, overridden by `LLM_MODEL` in `.env`.
- `config/rules.py` — **source of truth** for agent roles, rules, and which tools (skills) each agent gets. MCP registry reads this.
- `mcp/registry.py` — `load_mcp_context(agent_type)` maps agent → tools from `AVAILABLE_PLUGINS` in `plugins/core_tools.py`.
- `mcp/context_loader.py` — loads `mcp/mcp.json`, `rules/*.md`, `skills/*.md` into a combined context blob injected into system prompts.
- `plugins/core_tools.py` — real tool definitions: `tulis_kode` (write file), `baca_file` (read file), `cari_web` (DuckDuckGo search).
- `tools/agent_tools.py` — **legacy duplicate** of `plugins/core_tools.py`. Do not import from here; use `plugins/`.
- `tools/rag_engine.py` — FAISS + HuggingFace embeddings (`all-MiniLM-L6-v2`). Requires `faiss_index/` to exist. Build it first:
  ```python
  from tools.rag_engine import ingest_documents
  ingest_documents()
  ```
- `memory/memory.py` — Redis-backed chat history per `session_id`.
- `core/logger.py` — standard `logging` setup.

## Critical Quirks
- **Redis monkey-patch**: `main.py` patches `redis.from_url` at import time to force `protocol=2` (line 8-18). If you work with Redis directly, import `main` first or replicate the patch.
- **FAISS index required**: `get_relevant_context()` raises `RuntimeError` if `faiss_index/` is missing. Run `ingest_documents()` before any agent call that uses RAG.
- **`.env` validation**: `llm_config.py` raises `RuntimeError` if `NVIDIA_API_KEY` is missing or equals the placeholder `your_gemini_api_key_here`.
- **Rate limit**: `route_request()` sleeps 3s per call under a lock. Expect slow sequential runs.
- **Duplicate tools**: `tools/agent_tools.py` duplicates `plugins/core_tools.py`. Agents import from `plugins/`. Ignore `tools/agent_tools.py`.
- **No test framework**: Tests are ad-hoc scripts (`test_concurrent.py`, `test_redis_patch.py`). Run with `python test_concurrent.py`. No pytest, no lint, no typecheck config exists.

## Routing Keywords (case-insensitive)
| Trigger words | Agent |
|---|---|
| `draf`, `gaji`, `upah`, `surat`, `izin` | `admin_agent` |
| `kode`, `program`, `python`, `programing` | `coder_agent` |
| anything else | `casual_agent` |

## Data
- `data/*.txt` — RAG source documents (e.g. `kebijakan_umk.txt`, `ai_trading_guidelines.txt`). Re-ingest after editing.
- `skills/coding.md`, `rules/policy.md` — markdown injected into agent context. Currently placeholder content.
- `mcp/mcp.json` — empty `{}`. MCP server config lives here when populated.