"""Wrapper untuk mengubah tool MCP Remote menjadi LangChain Tool."""

from langchain_core.tools import BaseTool
from typing import Any, Dict
import asyncio
from mcp_core.client import mcp_manager

class RemoteMCPTool(BaseTool):
    """Tool wrapper yang meneruskan eksekusi ke server MCP remote."""
    
    server_name: str
    tool_name: str
    description: str

    def _run(self, **kwargs: Any) -> Any:
        """Eksekusi tool via asyncio.run karena MCP client bersifat asinkron."""
        return asyncio.run(mcp_manager.call_tool(self.server_name, self.tool_name, kwargs))

    async def _arun(self, **kwargs: Any) -> Any:
        """Eksekusi asinkron jika didukung oleh executor."""
        return await mcp_manager.call_tool(self.server_name, self.tool_name, kwargs)
