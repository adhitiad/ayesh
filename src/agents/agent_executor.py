"""Agent Executor: Mengelola tool calling loop secara otomatis menggunakan LangGraph."""

from typing import Annotated, Sequence, AsyncIterator
from typing_extensions import TypedDict
import time

from src.core.redis_patch import apply_redis_patch

apply_redis_patch()

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from src.agents.llm_config import get_llm
from src.memory.memory import get_memory_for_session
from src.core.logger import setup_logger

logger = setup_logger("agent_executor")

MAX_RETRIES = 5
RETRY_DELAY = 10


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


_graph_cache: dict = {}


def _cache_key(system_prompt: str, tools: list) -> str:
    tool_names = tuple(sorted(t.name for t in tools))
    return f"{system_prompt}|{tool_names}"


def create_agent_executor(system_prompt: str, tools: list):
    """Membuat agent executor dengan LangGraph (cached per kombinasi prompt+tools)."""
    key = _cache_key(system_prompt, tools)
    if key in _graph_cache:
        return _graph_cache[key]

    llm = get_llm()

    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm

    def agent_node(state: AgentState):
        """Node utama agent yang memanggil LLM dengan retry logic."""
        messages = state["messages"]
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                response = llm_with_tools.invoke(messages)
                return {"messages": [response]}
            except Exception as e:
                error_msg = str(e)
                last_error = e

                is_retryable = (
                    "429" in error_msg
                    or "Too Many Requests" in error_msg
                    or "503" in error_msg
                    or "overloaded" in error_msg.lower()
                    or "timeout" in error_msg.lower()
                    or "timed out" in error_msg.lower()
                    or "ReadTimeout" in error_msg
                )

                if is_retryable:
                    if attempt < MAX_RETRIES - 1:
                        if "429" in error_msg or "Too Many Requests" in error_msg:
                            wait_time = 15 * (attempt + 1)
                        else:
                            wait_time = RETRY_DELAY * (attempt + 1)
                        logger.warning(
                            f"API error (percobaan {attempt + 1}/{MAX_RETRIES}). Menunggu {wait_time} detik..."
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            f"API tetap gagal setelah {MAX_RETRIES} percobaan."
                        )
                        return {
                            "messages": [
                                AIMessage(
                                    content="Maaf, layanan AI sedang sibuk atau timeout. Silakan coba lagi dalam beberapa menit."
                                )
                            ]
                        }
                else:
                    raise e

        return {"messages": [AIMessage(content=f"Error: {str(last_error)}")]}

    tool_node = ToolNode(tools) if tools else None

    def should_continue(state: AgentState):
        """Decide apakah harus melanjutkan tool call atau selesai."""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    if tool_node:
        graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")

    if tool_node:
        graph.add_conditional_edges(
            "agent", should_continue, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge("agent", END)

    compiled = graph.compile()
    _graph_cache[key] = compiled
    return compiled


async def run_agent_executor_stream(
    user_input: str,
    session_id: str,
    system_prompt: str,
    tools: list,
    context: str = "",
) -> AsyncIterator[str]:
    """Menjalankan agent executor dengan streaming token-level."""
    memory = get_memory_for_session(session_id)

    full_prompt = system_prompt
    if context:
        full_prompt += f"\n\nReferensi:\n{context}"

    messages = [SystemMessage(content=full_prompt)]
    messages.extend(memory.messages)
    messages.append(HumanMessage(content=user_input))

    executor = create_agent_executor(system_prompt, tools)

    # Stream events dari graph
    async for event in executor.astream_events({"messages": messages}, version="v2"):
        kind = event.get("event")
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if hasattr(chunk, "content") and chunk.content:
                content = chunk.content
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            yield c.get("text", "")
                elif isinstance(content, str):
                    yield content
        elif kind == "on_tool_start":
            tool_name = event.get("name", "")
            yield f"\n[tool: {tool_name}]"
        elif kind == "on_tool_end":
            yield "\n"

    # Ambil final response untuk memori
    result = await executor.ainvoke({"messages": messages})
    final_message = result["messages"][-1]
    try:
        from src.core.usage import note_usage

        note_usage(final_message)
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("note_usage (tool loop) error: %s", _e)
    from src.core.text import extract_text

    raw = (
        final_message.content
        if hasattr(final_message, "content")
        else str(final_message)
    )
    ai_response = extract_text(raw)

    memory.add_user_message(user_input)
    memory.add_ai_message(ai_response)


def run_agent_executor(
    user_input: str,
    session_id: str,
    system_prompt: str,
    tools: list,
    context: str = "",
) -> str:
    """Menjalankan agent executor dengan memori dan RAG (sync, non-streaming)."""
    memory = get_memory_for_session(session_id)

    full_prompt = system_prompt
    if context:
        full_prompt += f"\n\nReferensi:\n{context}"

    messages = [SystemMessage(content=full_prompt)]
    messages.extend(memory.messages)
    messages.append(HumanMessage(content=user_input))

    executor = create_agent_executor(system_prompt, tools)

    result = executor.invoke({"messages": messages})

    final_message = result["messages"][-1]
    try:
        from src.core.usage import note_usage

        note_usage(final_message)
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("note_usage (tool loop) error: %s", _e)
    from src.core.text import extract_text

    ai_response = extract_text(
        final_message.content
        if hasattr(final_message, "content")
        else str(final_message)
    )

    memory.add_user_message(user_input)
    memory.add_ai_message(ai_response)

    return ai_response
