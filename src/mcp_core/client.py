"""MCP Client: Mengelola koneksi ke server MCP remote."""

import asyncio
import json
import os
import subprocess  # nosec B404 (transport MCP stdio)
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from src.core.observability.logger import setup_logger

load_dotenv()
logger = setup_logger("mcp_client")


class MCPClientManager:
    """Manajer untuk mengelola beberapa koneksi server MCP secara asinkron."""

    def __init__(self, config_path=None):
        if config_path is None:
            _here = os.path.dirname(os.path.abspath(__file__))
            _candidate = os.path.join(_here, "mcp.json")
            config_path = _candidate if os.path.isfile(_candidate) else "mcp_core/mcp.json"
        self.config_path = config_path
        self._connected_servers: dict[str, bool] = {}

    def _resolve_env_vars(self, env_dict: dict[str, str]) -> dict[str, str]:
        """Mengganti placeholder ${VAR} dengan nilai dari os.environ."""
        resolved_env = {}
        for key, value in env_dict.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                var_name = value[2:-1]
                resolved_env[key] = os.getenv(var_name, "")
            else:
                resolved_env[key] = value
        return resolved_env

    def _check_npx_available(self) -> bool:
        """Cek apakah npx tersedia di sistem."""
        try:
            npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
            result = subprocess.run(  # nosec B603 (argumen statis ["npx", "--version"], shell=False)
                [npx_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _resolve_env_in_args(self, args: list) -> list:
        """Resolve ${VAR} di dalam args list (termasuk di dalam string)."""
        import re

        resolved = []
        for arg in args:
            if isinstance(arg, str) and "${" in arg:

                def _replace(m):
                    var_name = m.group(1)
                    return os.getenv(var_name, m.group(0))

                arg = re.sub(r"\$\{(\w+)\}", _replace, arg)  # noqa: PLW2901
            resolved.append(arg)
        return resolved

    def _get_server_params(self, server_name: str) -> StdioServerParameters:
        """Mengambil parameter server dari config dan resolve env vars."""
        with open(self.config_path, encoding="utf-8") as f:
            config = json.load(f)

        server_config = config["mcpServers"].get(server_name)
        if not server_config:
            raise ValueError(f"Server {server_name} tidak ditemukan di config.")

        raw_env = server_config.get("env", {})
        resolved_env = self._resolve_env_vars(raw_env)
        final_env = {**os.environ, **resolved_env}

        command = server_config["command"]
        args = self._resolve_env_in_args(server_config["args"])

        # Windows wrapper untuk npx/uvx
        if os.name == "nt":
            if command.lower() == "npx":
                command = "cmd"
                args = ["/c", "npx", "-y", *args[1:]] if args[0] == "-y" else ["/c", "npx", *args]
            elif command.lower() == "uvx":
                # uvx biasanya sudah jalan di Windows, tapi tetap pakai shell
                pass

        return StdioServerParameters(command=command, args=args, env=final_env)

    async def _connect_server(self, server_name: str) -> ClientSession | None:
        """Mencoba menghubungkan ke satu server MCP."""
        try:
            params = self._get_server_params(server_name)
            read, write, _get_sid = await asyncio.wait_for(stdio_client(params).__aenter__(), timeout=30)
            session = await asyncio.wait_for(ClientSession(read, write).__aenter__(), timeout=30)
            await asyncio.wait_for(session.initialize(), timeout=30)
            return session
        except TimeoutError:
            logger.warning(f"Timeout saat menghubungkan ke {server_name} (30 detik)")
            return None
        except FileNotFoundError as e:
            logger.warning(f"Command tidak ditemukan untuk {server_name}: {e}")
            return None
        except Exception as e:
            error_msg = str(e)
            if "TaskGroup" in error_msg:
                logger.warning(
                    f"Server {server_name} gagal inisialisasi (kemungkinan kompatibilitas Windows): {error_msg[:100]}"
                )
            else:
                logger.warning(f"Gagal menghubungkan ke {server_name}: {error_msg[:100]}")
            return None

    async def list_all_tools(self) -> list[dict[str, Any]]:
        """Mengambil daftar semua tools dari semua server yang terdaftar."""
        all_tools: list[dict[str, Any]] = []

        if not self._check_npx_available():
            logger.warning("npx tidak ditemukan. Remote MCP servers tidak tersedia.")
            return all_tools

        with open(self.config_path, encoding="utf-8") as f:
            config = json.load(f)
            servers = config.get("mcpServers", {})

        for server_name, server_config in servers.items():
            if not isinstance(server_config, dict):
                logger.debug(f"Melewati server {server_name}: config bukan dict")
                continue

            # Deteksi remote SSE/HTTP
            is_remote = "url" in server_config
            is_stdio = "command" in server_config and "args" in server_config

            if not is_stdio and not is_remote:
                logger.debug(f"Melewati server {server_name}: bukan stdio maupun remote MCP server")
                continue

            try:
                if is_stdio:
                    params = self._get_server_params(server_name)
                    async with stdio_client(params) as (read, write, _get_sid):  # noqa: SIM117
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            result = await session.list_tools()
                            for tool in result.tools:
                                tool_data = (
                                    dict(tool.model_dump())
                                    if hasattr(tool, "model_dump")
                                    else {"name": getattr(tool, "name", "")}
                                )
                                tool_data["server"] = server_name
                                all_tools.append(tool_data)
                            self._connected_servers[server_name] = True
                            logger.info(f"Berhasil terhubung ke {server_name}: {len(result.tools)} tools tersedia")
                elif is_remote:
                    url = server_config.get("url")
                    if not url:
                        logger.debug(f"Server {server_name} remote tanpa url")
                        continue
                    headers = self._resolve_env_vars(server_config.get("headers", {}))
                    logger.debug(
                        f"Mencoba remote server {server_name} URL={url} headers_keys={list(headers.keys()) if headers else []}"
                    )
                    # Coba Streamable HTTP dulu, fallback ke SSE
                    try:
                        async with streamable_http_client(url=url) as (read, write, _get_sid):  # noqa: SIM117
                            async with ClientSession(read, write) as session:
                                await session.initialize()
                                result = await session.list_tools()
                                for tool in result.tools:
                                    tool_data = (
                                        dict(tool.model_dump())
                                        if hasattr(tool, "model_dump")
                                        else {"name": getattr(tool, "name", "")}
                                    )
                                    tool_data["server"] = server_name
                                    all_tools.append(tool_data)
                                self._connected_servers[server_name] = True
                                logger.info(
                                    f"Berhasil terhubung ke remote {server_name} via Streamable HTTP: {len(result.tools)} tools tersedia"
                                )
                    except Exception as e_http:
                        logger.debug(f"Streamable HTTP gagal untuk {server_name}: {str(e_http)[:200]}")
                        # Fallback ke SSE
                        try:
                            async with sse_client(url=url, headers=headers or None) as (  # noqa: SIM117
                                read,
                                write,
                            ):
                                async with ClientSession(read, write) as session:
                                    await session.initialize()
                                    result = await session.list_tools()
                                    for tool in result.tools:
                                        tool_data = (
                                            dict(tool.model_dump())
                                            if hasattr(tool, "model_dump")
                                            else {"name": getattr(tool, "name", "")}
                                        )
                                        tool_data["server"] = server_name
                                        all_tools.append(tool_data)
                                    self._connected_servers[server_name] = True
                                    logger.info(
                                        f"Berhasil terhubung ke remote {server_name} via SSE: {len(result.tools)} tools tersedia"
                                    )
                        except Exception as e_sse:
                            logger.debug(f"Remote server {server_name} tidak tersedia via SSE: {str(e_sse)[:200]}")
            except TimeoutError:
                logger.warning(f"Timeout saat mengambil tools dari {server_name}")
            except FileNotFoundError:
                logger.warning(f"Command untuk {server_name} tidak ditemukan")
            except Exception as e:
                error_msg = str(e)
                # Remote server failures are common without proper network / keys, log as debug
                if is_remote:
                    logger.debug(f"Remote server {server_name} tidak tersedia: {error_msg[:120]}")
                else:
                    logger.warning(f"Gagal mengambil tools dari {server_name}: {error_msg[:120]}")

        if not all_tools:
            logger.info("Tidak ada remote MCP tools yang berhasil dimuat. Menggunakan tools lokal saja.")

        return all_tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Memanggil tool tertentu dari server MCP tertentu."""
        try:
            with open(self.config_path, encoding="utf-8") as f:
                config = json.load(f)
            server_config = config["mcpServers"].get(server_name, {})
            is_remote = "url" in server_config
            is_stdio = "command" in server_config and "args" in server_config

            if is_stdio:
                params = self._get_server_params(server_name)
                async with stdio_client(params) as (read, write, _get_sid):  # noqa: SIM117
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)
                        return result
            elif is_remote:
                url = server_config.get("url")
                headers = self._resolve_env_vars(server_config.get("headers", {}))
                try:
                    async with (
                        streamable_http_client(url=url) as (read, write, _get_sid),
                        ClientSession(read, write) as session,
                    ):
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)
                        return result
                except Exception:
                    async with (
                        sse_client(url=url, headers=headers or None) as (
                            read,
                            write,
                        ),
                        ClientSession(read, write) as session,
                    ):
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)
                        return result
            else:
                return f"Error: Server {server_name} tidak mendukung stdio maupun remote"
        except TimeoutError:
            return f"Error: Timeout saat memanggil {tool_name} di {server_name}"
        except FileNotFoundError:
            return f"Error: Command untuk {server_name} tidak ditemukan"
        except Exception as e:
            return f"Error memanggil tool {tool_name} di {server_name}: {str(e)[:100]}"


mcp_manager = MCPClientManager()
