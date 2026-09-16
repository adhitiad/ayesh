import threading
import time
from typing import List
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_community.chat_message_histories import RedisChatMessageHistory
from sqlalchemy import create_engine, select, delete, and_
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from core.models import SessionMemory
from core.db_engine import get_engine
from memory.summarizer import summarize_session

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)

class OptimizedHybridMemory(BaseChatMessageHistory):
    """
    Hybrid Memory dengan Optimized Flush + Auto Summarization:
    - Redis: Active cache.
    - PostgreSQL: Long-term archive via periodic flush / lazy sync.
    - Auto Summarization: History diringkas otomatis saat threshold tercapai.
    """
    def __init__(self, session_id: str, flush_interval=60):
        self.session_id = session_id
        self.redis = RedisChatMessageHistory(session_id=session_id, url=REDIS_URL)
        self._pending_messages: List[BaseMessage] = []
        self._last_flush = time.time()
        self.flush_interval = flush_interval
        self._lock = threading.Lock()

    def _should_flush(self):
        return time.time() - self._last_flush > self.flush_interval

    def _flush_to_postgres(self):
        with self._lock:
            if not self._pending_messages:
                return
            
            with SessionLocal() as session:
                for msg in self._pending_messages:
                    role = "assistant" if isinstance(msg, AIMessage) else "user"
                    if isinstance(msg, SystemMessage):
                        role = "system"
                    new_mem = SessionMemory(
                        session_id=self.session_id,
                        role=role,
                        content=msg.content
                    )
                    session.add(new_mem)
                session.commit()
            
            self._pending_messages.clear()
            self._last_flush = time.time()
            
            # Auto summarization check
            summarize_session(self.session_id)

    def add_message(self, message: BaseMessage) -> None:
        # Always add to Redis for instant access
        self.redis.add_message(message)
        
        # Buffer message for Postgres
        with self._lock:
            self._pending_messages.append(message)
            
        # Flush if interval reached
        if self._should_flush():
            self._flush_to_postgres()

    def clear(self) -> None:
        self._flush_to_postgres()
        self.redis.clear()
        with SessionLocal() as session:
            session.execute(delete(SessionMemory).where(SessionMemory.session_id == self.session_id))
            session.commit()
        self._pending_messages.clear()

    def messages(self) -> List[BaseMessage]:
        # Check Redis first
        redis_msgs = self.redis.messages
        if redis_msgs:
            return redis_msgs
        
        # Fallback to Postgres
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
            # Sync back to Redis
            for m in msgs:
                self.redis.add_message(m)
            return msgs
