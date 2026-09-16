from typing import List
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_community.chat_message_histories import RedisChatMessageHistory
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from core.models import SessionMemory
from core.db_engine import get_engine

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Gunakan engine yang sudah dioptimasi dari core/db_engine
engine = get_engine()
SessionLocal = sessionmaker(bind=engine)

class HybridMemory(BaseChatMessageHistory):
    """
    Synchronized Memory System:
    - Redis: Fast cache for current active session.
    - PostgreSQL: Permanent long-term archive.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.redis = RedisChatMessageHistory(session_id=session_id, url=REDIS_URL)

    def add_message(self, message: BaseMessage) -> None:
        # 1. Sync to Redis (Fast Cache)
        self.redis.add_message(message)
        
        # 2. Sync to PostgreSQL (Long Term)
        # Optimasi: Gunakan bulk write atau batch flush di masa depan
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
        # Clear Redis
        self.redis.clear()
        # Clear Postgres
        with SessionLocal() as session:
            session.execute(
                delete(SessionMemory).where(SessionMemory.session_id == self.session_id)
            )
            session.commit()

    def messages(self) -> List[BaseMessage]:
        # Priority 1: Get from Redis (Fastest)
        redis_msgs = self.redis.messages
        if redis_msgs:
            return redis_msgs
            
        # Priority 2: Fallback to PostgreSQL (Archive)
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
            
            # Sync back to Redis for next calls
            for m in msgs:
                self.redis.add_message(m)
                
            return msgs
