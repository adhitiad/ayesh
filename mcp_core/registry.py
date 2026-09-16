"""MCP Registry: Memilih plugins berdasarkan rules agent."""

from pathlib import Path
import sys
import asyncio
from typing import List, Any, Callable

from config.rules import AGENT_RULES
from plugins.core_tools import AVAILABLE_PLUGINS
from mcp_core.client import mcp_manager
from mcp_core.tool_wrapper import RemoteMCPTool

def load_mcp_context(agent_type: str) -> tuple[str, List[Any]]:
    """
    Membaca AGENT_RULES dari config/rules.py berdasarkan agent_type.
    Menggabungkan tools lokal (plugins) dan tools remote (MCP servers).
    
    Returns:
        tuple: (system_prompt, list_of_tools)
    """
    if agent_type not in AGENT_RULES:
        raise ValueError(f"Agent type '{agent_type}' tidak dikenal. Pilihan: {list(AGENT_RULES.keys())}")
    
    agent_config = AGENT_RULES[agent_type]
    skills = agent_config.get("skills", [])
    
    # 1. Ambil Tools Lokal (Plugins)
    tools = []
    for skill in skills:
        if skill in AVAILABLE_PLUGINS:
            tools.append(AVAILABLE_PLUGINS[skill])
    
    # 2. Ambil Tools Remote (MCP Servers)
    try:
        remote_tools_info = asyncio.run(mcp_manager.list_all_tools())
        for rt in remote_tools_info:
            t_name = rt.get("name", "")
            if any(skill in t_name for skill in skills):
                wrapped_tool = RemoteMCPTool(
                    server_name=rt["server"],
                    tool_name=t_name,
                    description=rt.get("description", "Remote MCP Tool")
                )
                tools.append(wrapped_tool)
    except Exception as e:
        pass  # Remote MCP tools adalah opsional, tidak wajib

    role = agent_config.get("role", "Agent")
    rules = agent_config.get("rules", [])
    rules_text = "\n".join([f"- {r}" for r in rules])
    
    system_prompt = (
        f"You are {role}. "
        f"Follow these rules:\n{rules_text}\n"
        f"Available tools: {', '.join(skills) if skills else 'None'}."
    )
    
    return system_prompt, tools
