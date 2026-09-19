"""Wrapper untuk mengubah tool MCP Remote menjadi LangChain Tool."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langchain_core.tools import BaseTool

from src.mcp_core.client import mcp_manager

_executor = ThreadPoolExecutor(max_workers=2)

class RemoteMCPTool(BaseTool):
    """Tool wrapper yang meneruskan eksekusi ke server MCP remote."""

    server_name: str
    tool_name: str
    description: str

    def _run(self, **kwargs: Any) -> Any:
        """Eksekusi sync: gunakan thread pool jika event loop sudah aktif."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            future = _executor.submit(asyncio.run, mcp_manager.call_tool(self.server_name, self.tool_name, kwargs))
            return future.result(timeout=60)
        return asyncio.run(mcp_manager.call_tool(self.server_name, self.tool_name, kwargs))

    async def _arun(self, **kwargs: Any) -> Any:
        """Eksekusi asinkron jika didukung oleh executor."""
        return await mcp_manager.call_tool(self.server_name, self.tool_name, kwargs)
