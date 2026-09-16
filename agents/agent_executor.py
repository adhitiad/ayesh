"""Agent Executor: Mengelola tool calling loop secara otomatis menggunakan LangGraph."""

from typing import Annotated, Sequence
from typing_extensions import TypedDict
import time

# Patch redis to force RESP2 protocol for compatibility with old Redis server
from core.redis_patch import apply_redis_patch
apply_redis_patch()

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agents.llm_config import get_llm
from memory.memory import get_memory_for_session
from tools.rag_engine import get_relevant_context
from core.logger import setup_logger

logger = setup_logger("agent_executor")

MAX_RETRIES = 5
RETRY_DELAY = 10


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


def create_agent_executor(system_prompt: str, tools: list):
    """Membuat agent executor dengan LangGraph."""
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
                    "503" in error_msg
                    or "overloaded" in error_msg.lower()
                    or "timeout" in error_msg.lower()
                    or "timed out" in error_msg.lower()
                    or "ReadTimeout" in error_msg
                )

                if is_retryable:
                    if attempt < MAX_RETRIES - 1:
                        wait_time = RETRY_DELAY * (attempt + 1)
                        logger.warning(f"NVIDIA API error (percobaan {attempt + 1}/{MAX_RETRIES}). Menunggu {wait_time} detik...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"NVIDIA API tetap gagal setelah {MAX_RETRIES} percobaan.")
                        return {"messages": [AIMessage(content="Maaf, layanan AI sedang sibuk atau timeout. Silakan coba lagi dalam beberapa menit.")]}
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
        graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge("agent", END)

    return graph.compile()


def run_agent_executor(
    user_input: str,
    session_id: str,
    system_prompt: str,
    tools: list,
    context: str = "",
) -> str:
    """
    Menjalankan agent executor dengan memori dan RAG.
    """
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
    ai_response = final_message.content if hasattr(final_message, "content") else str(final_message)

    memory.add_user_message(user_input)
    memory.add_ai_message(ai_response)

    return ai_response
