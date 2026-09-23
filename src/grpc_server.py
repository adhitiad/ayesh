"""gRPC server untuk Ayesh Desktop — wrapping route_request."""

import asyncio
import concurrent.futures
import logging
import os

import grpc

import ayesh_pb2
import ayesh_pb2_grpc
from main import route_request
from src.core.db.db_engine import get_engine
from src.core.observability.observability import health_check
from src.core.system.error_handling import generate_request_id
from src.core.system.redis_patch import apply_redis_patch

apply_redis_patch()

logger = logging.getLogger("ayesh.grpc")
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


class AyeshServicer(ayesh_pb2_grpc.AyeshServiceServicer):
    async def ChatStream(self, request_iterator, context):
        """Bidirectional streaming untuk chat."""
        try:
            async for msg in request_iterator:
                if msg.interrupt:
                    yield ayesh_pb2.ChatChunk(
                        token="",  # nosec B106 — teks streaming, bukan credential
                        tool_calls=[],
                        done=True,
                        usage=ayesh_pb2.Usage(
                            prompt_tokens=0,
                            completion_tokens=0,
                            cost_usd=0.0,
                        ),
                    )
                    return

                request_id = generate_request_id()
                session_id = msg.session_id or f"grpc_{request_id[:8]}"
                loop = asyncio.get_event_loop()

                result = await loop.run_in_executor(
                    _executor,
                    route_request,
                    msg.message,
                    session_id,
                    0,
                    request_id,
                )

                if result is None:
                    result = {}

                content = result.get("content", "")
                usage = result.get("usage", {})
                tool_calls_data = result.get("tool_calls", [])

                if content:
                    chunk_size = max(1, len(content) // max(1, len(content) // 10 + 1))
                    for i in range(0, len(content), chunk_size):
                        yield ayesh_pb2.ChatChunk(
                            token=content[i : i + chunk_size],
                            tool_calls=[],
                            done=False,
                            usage=None,
                        )

                if tool_calls_data:
                    for tc in tool_calls_data:
                        yield ayesh_pb2.ChatChunk(
                            token="",  # nosec B106 — teks streaming, bukan credential
                            tool_calls=[
                                ayesh_pb2.ToolCall(
                                    name=tc.get("name", ""),
                                    status=tc.get("status", "running"),
                                    progress=tc.get("progress", 0),
                                    result=tc.get("result", ""),
                                )
                            ],
                            done=False,
                            usage=None,
                        )

                yield ayesh_pb2.ChatChunk(
                    token="",  # nosec B106 — teks streaming, bukan credential
                    tool_calls=[],
                    done=True,
                    usage=ayesh_pb2.Usage(
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        cost_usd=usage.get("cost_usd", 0.0),
                    ),
                )

        except Exception as e:
            logger.error("ChatStream error: %s", e)
            yield ayesh_pb2.ChatChunk(
                token=f"Error: {e!s}",
                tool_calls=[],
                done=True,
                usage=ayesh_pb2.Usage(prompt_tokens=0, completion_tokens=0, cost_usd=0.0),
            )

    async def Chat(self, request, context):
        """Chat unary."""
        try:
            request_id = generate_request_id()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                _executor,
                route_request,
                request.message,
                request.session_id or f"grpc_{request_id[:8]}",
                0,
                request_id,
            )

            if result is None:
                result = {}

            content = result.get("content", "")
            tool_calls_data = result.get("tool_calls", [])
            usage = result.get("usage", {})

            return ayesh_pb2.ChatResponse(
                content=content,
                tool_calls=[
                    ayesh_pb2.ToolCall(
                        name=tc.get("name", ""),
                        status=tc.get("status", "completed"),
                        progress=tc.get("progress", 0),
                        result=tc.get("result", ""),
                    )
                    for tc in tool_calls_data
                ],
                usage=ayesh_pb2.Usage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    cost_usd=usage.get("cost_usd", 0.0),
                ),
                agent_type=result.get("agent_type", "casual_agent"),
                request_id=request_id,
            )
        except Exception as e:
            logger.error("Chat error: %s", e)
            return ayesh_pb2.ChatResponse(
                content=f"Error: {e!s}",
                agent_type="error",
                request_id="",
            )

    async def ListFiles(self, request, context):
        """List files di directory."""
        try:
            from src.plugins.core_tools import _safe_path

            path = _safe_path(request.path)
            files = []
            for entry in os.scandir(path):
                files.append(
                    ayesh_pb2.FileEntry(
                        name=entry.name,
                        type="directory" if entry.is_dir() else "file",
                        size=entry.stat().st_size if entry.is_file() else 0,
                    )
                )
            return ayesh_pb2.ListFilesResponse(files=files)
        except Exception as e:
            logger.error("ListFiles error: %s", e)
            return ayesh_pb2.ListFilesResponse(files=[])

    async def ReadFile(self, request, context):
        """Baca file content."""
        try:
            from src.plugins.core_tools import _safe_path

            path = _safe_path(request.path)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            return ayesh_pb2.ReadFileResponse(content=content)
        except Exception as e:
            logger.error("ReadFile error: %s", e)
            return ayesh_pb2.ReadFileResponse(content=f"Error: {e!s}")

    async def WriteFile(self, request, context):
        """Tulis file content."""
        try:
            from src.plugins.core_tools import _safe_path

            path = _safe_path(request.path)
            with open(path, "w", encoding="utf-8") as f:
                f.write(request.content)
            return ayesh_pb2.WriteFileResponse(success=True, message="File saved")
        except Exception as e:
            logger.error("WriteFile error: %s", e)
            return ayesh_pb2.WriteFileResponse(success=False, message=str(e))

    async def ListSessions(self, request, context):
        """List sessions."""
        try:
            from sqlalchemy import select

            from src.core.db.models import Session as SessionModel

            engine = get_engine()
            sessions = []
            with engine.connect() as conn:
                result = conn.execute(select(SessionModel).order_by(SessionModel.created_at.desc()).limit(20))
                for row in result:
                    sessions.append(
                        ayesh_pb2.Session(
                            id=str(row.id),
                            agent_type=row.agent_type or "casual_agent",
                            created_at=str(row.created_at) if row.created_at else "",
                            last_message=row.context[:100] if row.context else "",
                        )
                    )
            return ayesh_pb2.ListSessionsResponse(sessions=sessions)
        except Exception as e:
            logger.error("ListSessions error: %s", e)
            return ayesh_pb2.ListSessionsResponse(sessions=[])

    async def GetSession(self, request, context):
        """Get session by ID."""
        try:
            from sqlalchemy import select

            from src.core.db.models import Session as SessionModel

            engine = get_engine()
            with engine.connect() as conn:
                result = conn.execute(select(SessionModel).where(SessionModel.id == request.id))
                row = result.first()
                if row:
                    return ayesh_pb2.Session(
                        id=str(row.id),
                        agent_type=row.agent_type or "casual_agent",
                        created_at=str(row.created_at) if row.created_at else "",
                        last_message=row.context[:100] if row.context else "",
                    )
            return ayesh_pb2.Session()
        except Exception as e:
            logger.error("GetSession error: %s", e)
            return ayesh_pb2.Session()

    async def ListSkills(self, request, context):
        """List skills."""
        try:
            from src.plugins.core_tools import AVAILABLE_PLUGINS

            skills = []
            for name, plugin in AVAILABLE_PLUGINS.items():
                skills.append(
                    ayesh_pb2.Skill(
                        name=name,
                        description=getattr(plugin, "description", ""),
                        installed=True,
                    )
                )
            return ayesh_pb2.ListSkillsResponse(skills=skills)
        except Exception as e:
            logger.error("ListSkills error: %s", e)
            return ayesh_pb2.ListSkillsResponse(skills=[])

    async def InstallSkill(self, request, context):
        """Install or uninstall skill."""
        try:
            if request.uninstall:
                from install_agents import uninstall_skill

                uninstall_skill(request.name)
                return ayesh_pb2.Status(success=True, message=f"Uninstalled {request.name}")
            else:
                from install_agents import install_skill

                install_skill(request.name)
                return ayesh_pb2.Status(success=True, message=f"Installed {request.name}")
        except Exception as e:
            logger.error("InstallSkill error: %s", e)
            return ayesh_pb2.Status(success=False, message=str(e))

    async def GetConfig(self, request, context):
        """Get config."""
        return ayesh_pb2.Config(
            provider=os.getenv("LLM_PROVIDER", "groq"),
            api_key="",
            model=os.getenv("MODEL", ""),
            host=os.getenv("API_HOST", "127.0.0.1"),
            port=int(os.getenv("API_PORT", "8080")),
            grpc_host="localhost",
            grpc_port=50051,
        )

    async def SetConfig(self, request, context):
        """Set config."""
        try:
            if request.config.provider:
                os.environ["LLM_PROVIDER"] = request.config.provider
            if request.config.model:
                os.environ["MODEL"] = request.config.model
            return ayesh_pb2.Status(success=True, message="Config updated")
        except Exception as e:
            logger.error("SetConfig error: %s", e)
            return ayesh_pb2.Status(success=False, message=str(e))

    async def HealthCheck(self, request, context):
        """Health check."""
        h = health_check()
        return ayesh_pb2.HealthResponse(
            healthy=(h.postgres and h.redis),
            version="0.1.0",
            postgres_connected=h.postgres,
            redis_connected=h.redis,
        )


async def serve():
    """Mulai gRPC server."""
    server = grpc.aio.server(
        concurrent.futures.ThreadPoolExecutor(max_workers=4),
        options=[
            ("grpc.so_reuseport", 0),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
        ],
    )
    ayesh_pb2_grpc.add_AyeshServiceServicer_to_server(AyeshServicer(), server)
    server.add_insecure_port("[::]:50051")
    await server.start()
    logger.info("gRPC server running on :50051")
    await server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
