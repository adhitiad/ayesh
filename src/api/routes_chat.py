import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from main import route_request
from src.agents.agent_executor import run_agent_executor_stream
from src.api.models import ChatRequest
from src.core.auth.approval import set_current_agent_type
from src.core.auth.audit import append_audit
from src.core.auth.auth import require_auth
from src.core.memory.monologue import get_latest_monologue, get_role_for_agent
from src.core.routing.adaptive_router import classify_agent
from src.core.system.error_handling import (
    generate_request_id,
    log_internal_error,
    safe_error_response,
)
from src.mcp_core.registry import load_mcp_context
from src.mcp_core.skills import get_skills_block
from src.mcp_core.tool_validator import validate_tools_for_agent
from src.plugins.core_tools import get_preferences_block

router = APIRouter()


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    require_auth(request)
    session_id = req.session_id or f"api_{uuid.uuid4().hex[:8]}"

    async def _gen():
        data = json.dumps({"stage": "routing", "session_id": session_id})
        yield f"event: status\ndata: {data}\n\n"
        task = asyncio.create_task(asyncio.to_thread(route_request, req.message, session_id))
        while True:
            done, _ = await asyncio.wait({task}, timeout=15)
            if done:
                break
            yield ": ping\n\n"
        try:
            result = task.result()
            yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
        except Exception as e:
            request_id = generate_request_id()
            log_internal_error(request_id, e, context="chat_stream")
            msg = str(e)
            code = "rate_limited" if ("429" in msg or "Too Many Requests" in msg) else "error"
            error_data = json.dumps({"code": code, "request_id": request_id, "detail": "Terjadi kesalahan internal."})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post("/chat/stream/tokens")
async def chat_stream_tokens(req: ChatRequest, request: Request):
    require_auth(request)
    session_id = req.session_id or f"api_{uuid.uuid4().hex[:8]}"
    user_input = req.message

    # Routing & prompt building (sync, cepat)
    agent_type = classify_agent(user_input, user_id=session_id)
    # P1.3 -- Set agent_type context for MCP policy enforcement
    try:
        set_current_agent_type(agent_type)
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("set_current_agent_type error: %s", _e)
    system_prompt, default_tools = load_mcp_context(
        agent_type,
        session_nama=None,
        session_context=None,
    )
    skill_block = get_skills_block()
    # Monologue terakhir (sama seperti main.py route_request)
    try:
        latest_monologue = get_latest_monologue(session_id, agent_type)
        if latest_monologue:
            system_prompt += f"\n\n## Monologue ({latest_monologue.role})\n{latest_monologue.content}"
        else:
            system_prompt += f"\n\n## Monologue ({get_role_for_agent(agent_type)})\n[No monologue yet.]"
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("monologue load error: %s", _e)
    augmented_prompt = system_prompt + skill_block
    # Preferensi
    try:
        _pref_block = get_preferences_block()
        if _pref_block:
            augmented_prompt += f"\n\n## {_pref_block}"
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("preferences block error: %s", _e)
    filtered_tools = default_tools
    validated_tools = validate_tools_for_agent(agent_type, filtered_tools)

    async def _gen():
        data = json.dumps({"stage": "streaming", "agent": agent_type, "session_id": session_id})
        yield f"event: status\ndata: {data}\n\n"
        try:
            async for token in run_agent_executor_stream(
                user_input=user_input,
                session_id=session_id,
                system_prompt=augmented_prompt,
                tools=validated_tools,
                context="",
            ):
                if token:
                    token_data = json.dumps({"token": token})
                    yield f"event: token\ndata: {token_data}\n\n"
            done_data = json.dumps({"status": "complete"})
            yield f"event: done\ndata: {done_data}\n\n"
        except Exception as e:
            request_id = generate_request_id()
            log_internal_error(request_id, e, context="chat_stream_tokens")
            msg = str(e)
            code = "rate_limited" if ("429" in msg or "Too Many Requests" in msg) else "error"
            error_data = json.dumps({"code": code, "request_id": request_id, "detail": "Terjadi kesalahan internal."})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post("/chat")
def chat(req: ChatRequest, request: Request):
    require_auth(request)
    session_id = req.session_id or f"api_{uuid.uuid4().hex[:8]}"
    request_id = generate_request_id()
    try:
        result = route_request(user_input=req.message, session_id=session_id)
        try:
            append_audit(
                "chat",
                actor=session_id,
                details={
                    "agent": result.get("agent_type"),
                    "tools": result.get("tools_used", []),
                    "msg": req.message[:200],
                },
            )
        except Exception as _e:
            import logging

            logging.getLogger(__name__).debug("audit chat_log error: %s", _e)
        result["request_id"] = request_id
        return result
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "Too Many Requests" in error_msg:
            raise HTTPException(
                status_code=429,
                detail="LLM API rate limit terlampaui. Coba lagi dalam beberapa detik.",
            ) from e
        safe_resp = safe_error_response(e, request_id, context="chat")
        raise HTTPException(status_code=500, detail=safe_resp) from e
