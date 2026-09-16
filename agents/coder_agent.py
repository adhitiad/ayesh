"""Coder Agent - Sub-agen untuk tugas pemrograman dengan Tool Calling manual."""

import os
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agents.llm_config import get_llm
from memory.memory import get_memory_for_session
from tools.rag_engine import get_relevant_context
from plugins.core_tools import AVAILABLE_PLUGINS
from core.logger import setup_logger

logger = setup_logger("coder_agent")

SYSTEM_PROMPT = (
    "Anda adalah Senior Software Engineer. Saat membahas sistem Reinforcement Learning, "
    "Anda selalu memastikan arsitektur diletakkan di dalam file agent.py dan env.py. "
    "Berikan kode yang terstruktur dengan baik.\n\n"
    "Berikut adalah informasi referensi internal untuk membantu Anda: {context}"
)

tools = [AVAILABLE_PLUGINS["tulis_kode"], AVAILABLE_PLUGINS["baca_file"]]

llm = get_llm().bind_tools(tools)


def run_coder_agent(user_input: str, session_id: str) -> str:
    """Jalankan Coder Agent dengan Tool Calling, Memori Redis, dan RAG."""
    context = get_relevant_context(user_input, k=2)
    memory = get_memory_for_session(session_id)
    
    # Build initial message list
    messages = [SystemMessage(content=SYSTEM_PROMPT.format(context=context))]
    messages.extend(memory.messages)
    messages.append(HumanMessage(content=user_input))

    # Tool calling loop
    while True:
        response = llm.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            logger.info(f"[{session_id}] [Tool Call] {tool_name}({tool_args})")
            
            tool_func = AVAILABLE_PLUGINS.get(tool_name)
            if tool_func:
                tool_result = tool_func.invoke(tool_args)
            else:
                tool_result = f"Error: Tool {tool_name} tidak ditemukan."
            
            messages.append(ToolMessage(
                content=str(tool_result), 
                tool_call_id=tool_call["id"]
            ))

        ai_response = response.content
    memory.add_user_message(user_input)
    memory.add_ai_message(ai_response)
    
    return ai_response
