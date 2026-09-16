from typing import List
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from core.models import SessionMemory

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class PostgresMemory(BaseChatMessageHistory):
    """Custom LangChain chat history using SQLAlchemy and PostgreSQL."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id

    def add_message(self, message: BaseMessage) -> None:
        role = "assistant" if isinstance(message, AIMessage) else "user"
        if isinstance(message, SystemMessage):
            role = "system"
        
        with SessionLocal() as session:
            new_mem = SessionMemory(
                session_id=self.session_id,
                role=role,
                content=message.content
            )
            session.add(new_mem)
            session.commit()

    def clear(self) -> None:
        with SessionLocal() as session:
            session.execute(
                delete(SessionMemory).where(SessionMemory.session_id == self.session_id)
            )
            session.commit()

    def messages(self) -> List[BaseMessage]:
        with SessionLocal() as session:
            stmt = select(SessionMemory).where(SessionMemory.session_id == self.session_id).order_by(SessionMemory.timestamp)
            results = session.execute(stmt).scalars().all()
            
            msgs = []
            for r in results:
                if r.role == "assistant":
                    msgs.append(AIMessage(content=r.content))
                elif r.role == "system":
                    msgs.append(SystemMessage(content=r.content))
                else:
                    msgs.append(HumanMessage(content=r.content))
            return msgs
