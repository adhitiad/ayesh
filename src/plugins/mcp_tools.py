"""MCP tool: panggil_mcp."""

import asyncio
import json as _json

from langchain_core.tools import tool

from src.plugins.tool_error import tool_error_from_exception

_MCP_BLOCKED_SERVERS = {"filesystem"}


@tool
def panggil_mcp(server: str, tool: str, args_json: str = "{}") -> str:
    """Memanggil tool server MCP remote on-demand (lazy, tanpa startup cost).

    Daftar server lihat mcp_core/mcp.json (tavily, exa, firecrawl, github,
    sequential-thinking, context7, ...). Server 'filesystem' diblokir —
    pakai tulis_kode/baca_file untuk file lokal.

    Args:
        server: Nama server di mcp.json. Contoh: "tavily", "exa".
        tool: Nama tool di server itu. Contoh: "tavily_search".
        args_json: Argumen sebagai JSON string. Contoh: '{"query": "harga emas"}'.
    """
    try:
        from src.mcp_core.client import mcp_manager

        server = server.strip()
        if server in _MCP_BLOCKED_SERVERS:
            return f"Error: Server '{server}' diblokir. Untuk file lokal pakai tulis_kode/baca_file."
        try:
            args = _json.loads(args_json) if args_json.strip() else {}
        except _json.JSONDecodeError:
            return "Error: args_json bukan JSON valid."
        if not isinstance(args, dict):
            return "Error: args_json harus object JSON."

        # P1.3 — Enforce MCP policy: server + tool must be allowlisted
        try:
            from src.core.auth.approval import check_mcp_policy

            allowed, deny_msg = check_mcp_policy(server, tool)
            if not allowed:
                return deny_msg
        except Exception as exc:
            return tool_error_from_exception(exc, "MCP policy denied")

        # P1.4 — Approval gate: fail-closed on exception
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "panggil_mcp",
                {"server": server, "tool": tool},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as exc:
            return tool_error_from_exception(exc, "approval gate denied")

        async def _call():
            return await mcp_manager.call_tool(server, tool, args)

        result = asyncio.run(_call())
        from src.core.llm.text import extract_text

        if hasattr(result, "content") and result.content:
            text = extract_text(result.content, sep="\n\n")
            return text or str(result)
        return str(result)
    except Exception as e:
        return tool_error_from_exception(e)
