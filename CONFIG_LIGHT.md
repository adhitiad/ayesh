# Konfigurasi Ringan Sementara

Tanggal: 2026-09-16

## Tujuan
Mengurangi beban API NVIDIA NIM untuk menghindari timeout/503/500 saat menjalankan Multi-Agent dengan MCP.

## Perubahan Aktif

### 1. main.py
- RAG context dinonaktifkan: `context = ""` // sebelumnya `get_relevant_context(user_input, k=1)`
- Rules & Skills dibatasi: `rules_text = rules_text[:400]`, `skills_text = skills_text[:400]`
- Context loader tetap dijalankan untuk routing, namun tidak disuntikkan ke LLM

### 2. agents/agent_executor.py
- `MAX_RETRIES = 5`
- `RETRY_DELAY = 10`
- Retry mencakup: 503, overloaded, timeout, ReadTimeout

### 3. mcp_core/client.py
- Windows wrapper untuk npx: command diubah ke `cmd` dengan args `[/c, npx, -y, ...]`
- Remote MCP servers yang aktif:
  - github : npx @modelcontextprotocol/server-github
  - filesystem : npx @modelcontextprotocol/server-filesystem E:/code/fr
  - memory : npx @modelcontextprotocol/server-memory
  - time : uvx mcp-server-time

### 4. mcp_core/mcp.json
- Server fetch dihapus karena 404
- Format JSON tanpa BOM, UTF-8

## Status
- Multi-Agent run Fase 9 selesai tanpa error
- File otonom kalkulator.py berhasil dibuat
- MCP remote servers terhubung di Windows

## Kembalikan ke mode penuh
1. Aktifkan kembali RAG: ganti `context = ""` dengan `get_relevant_context(user_input, k=2)`
2. Naikkan batas rules/skills ke panjang penuh
3. Turunkan MAX_RETRIES sesuai kebutuhan produksi
