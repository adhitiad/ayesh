"""Admin Agent - Sub-agen untuk tugas administratif/surat resmi."""

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory

from agents.llm_config import get_llm
from memory.memory import get_memory_for_session
from tools.rag_engine import get_relevant_context
from plugins.core_tools import AVAILABLE_PLUGINS
from core.logger import setup_logger

logger = setup_logger("admin_agent")

SYSTEM_PROMPT = (
    "Anda adalah Kepala Sub Bagian Humas di Universitas Subang. "
    "Tugas Anda adalah membuat draf surat resmi, menggunakan gaya bahasa birokrasi "
    "yang formal, baku, dan profesional. Selalu lindungi data staf lain.\n\n"
    "Berikut adalah informasi referensi internal untuk membantu Anda: {context}"
)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ]
)

chain = prompt | get_llm()

def get_session_history(session_id: str):
    return get_memory_for_session(session_id)

runnable_with_history = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history",
)


def run_admin_agent(user_input: str, session_id: str) -> str:
    """Jalankan Admin Agent dengan memori Redis dan RAG."""
    context = get_relevant_context(user_input, k=2)
    
    logger.info(f"[{session_id}] Menjalankan Admin Agent dengan RAG context")
    response = runnable_with_history.invoke(
        {"input": user_input, "context": context},
        config={"configurable": {"session_id": session_id}},
    )
    return response.content
