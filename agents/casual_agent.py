"""Casual Agent - Sub-agen untuk percakapan santai dengan Tool Calling manual."""

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from agents.llm_config import get_llm
from memory.memory import get_memory_for_session
from plugins.core_tools import AVAILABLE_PLUGINS
from core.logger import setup_logger

logger = setup_logger("casual_agent")

SYSTEM_PROMPT = "Anda adalah asisten AI yang ramah, santai, dan membantu percakapan umum."

tools = list(AVAILABLE_PLUGINS.values())

llm = get_llm().bind_tools(tools)


def run_casual_agent(user_input: str, session_id: str) -> str:
    """Jalankan Casual Agent dengan Tool Calling manual dan Memori Redis."""
    memory = get_memory_for_session(session_id)
    
    # Build initial message list
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
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

