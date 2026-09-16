import asyncio
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import tools_condition, ToolNode
from langchain_core.messages import HumanMessage
from agents.llm_config import get_llm
from core.models import SessionMemory
from core.db_engine import get_engine
from sqlalchemy.orm import sessionmaker

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)

class AsyncAgentState(dict):
    messages: list
    tools: list
    system_prompt: str

async def async_call_model(state: AsyncAgentState):
    llm = get_llm()
    system_prompt = state.get("system_prompt", "")
    messages = [HumanMessage(content=system_prompt)] + state["messages"]
    response = await llm.ainvoke(messages)
    return {"messages": state["messages"] + [response]}

async def async_agent_executor(user_input: str, session_id: str, system_prompt: str, tools: list):
    # Load history
    with SessionLocal() as session:
        from sqlalchemy import select
        history = session.execute(
            select(SessionMemory).where(SessionMemory.session_id == session_id)
        ).scalars().all()
    
    # Build graph
    builder = StateGraph(AsyncAgentState)
    builder.add_node("agent", async_call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")
    
    graph = builder.compile()
    
    result = await graph.ainvoke({
        "messages": [HumanMessage(content=user_input)],
        "tools": tools,
        "system_prompt": system_prompt
    })
    return result["messages"][-1].content
