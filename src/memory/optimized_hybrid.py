import os
import threading
import time

import redis
from dotenv import load_dotenv
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from src.core.db.db_engine import get_engine, with_retry
from src.core.db.models import SessionMemory
from src.memory.summarizer import summarize_session

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)


class ResilientRedisClient:
    """Redis client dengan retry/backoff dan circuit breaker."""

    def __init__(self, url: str, max_retries=3, base_delay=0.2, max_delay=2.0):
        self.url = url
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._client = None
        self._failure_count = 0
        self._circuit_open = False
        self._last_failure_time = 0
        self._circuit_timeout = 30  # detik sebelum coba lagi

    def _get_client(self):
        if self._client is None:
            self._client = redis.from_url(
                self.url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
        return self._client

    def _circuit_check(self):
        if self._circuit_open:
            if time.time() - self._last_failure_time > self._circuit_timeout:
                self._circuit_open = False
                self._failure_count = 0
            else:
                raise redis.ConnectionError("Circuit breaker open - Redis unavailable")

    def _execute_with_retry(self, func, *args, **kwargs):
        self._circuit_check()
        last_error: Exception = redis.ConnectionError("retry failed")
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except redis.RedisError as e:
                last_error = e
                self._failure_count += 1
                self._last_failure_time = time.time()
                if self._failure_count >= 5:
                    self._circuit_open = True
                if attempt < self.max_retries - 1:
                    delay = min(self.base_delay * (2**attempt), self.max_delay)
                    time.sleep(delay)
                    # Reset client on connection error
                    if "Connection" in str(e):
                        self._client = None
                    continue
                raise
        raise last_error

    def get(self, key):
        return self._execute_with_retry(self._get_client().get, key)

    def set(self, key, value, ex=None):
        return self._execute_with_retry(self._get_client().set, key, value, ex=ex)

    def lpush(self, key, *values):
        return self._execute_with_retry(self._get_client().lpush, key, *values)

    def lrange(self, key, start, end):
        return self._execute_with_retry(self._get_client().lrange, key, start, end)

    def delete(self, key):
        return self._execute_with_retry(self._get_client().delete, key)

    def exists(self, key):
        return self._execute_with_retry(self._get_client().exists, key)

    def expire(self, key, seconds):
        return self._execute_with_retry(self._get_client().expire, key, seconds)


# Singleton Redis client
_redis_client = ResilientRedisClient(REDIS_URL)


class ResilientRedisChatMessageHistory:
    """Wrapper RedisChatMessageHistory dengan retry/backoff."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.key = f"chat_history:{session_id}"

    def add_message(self, message):
        from langchain_core.messages import AIMessage, HumanMessage

        role = (
            "assistant"
            if isinstance(message, AIMessage)
            else ("user" if isinstance(message, HumanMessage) else "system")
        )
        import json

        msg_data = json.dumps({"role": role, "content": message.content})
        _redis_client.lpush(self.key, msg_data)
        _redis_client.expire(self.key, 86400)  # 24h TTL

    @property
    def messages(self):
        import json

        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        try:
            raw = _redis_client.lrange(self.key, 0, -1)
            msgs = []
            for item in reversed(raw):  # lpush = reverse order
                data = json.loads(item)
                role = data.get("role", "user")
                content = data.get("content", "")
                if role == "assistant":
                    msgs.append(AIMessage(content=content))
                elif role == "system":
                    msgs.append(SystemMessage(content=content))
                else:
                    msgs.append(HumanMessage(content=content))
            return msgs
        except redis.RedisError:
            return []

    def clear(self):
        _redis_client.delete(self.key)


class OptimizedHybridMemory(BaseChatMessageHistory):
    """
    Hybrid Memory dengan Optimized Flush + Auto Summarization:
    - Redis: Active cache (dengan retry/backoff).
    - PostgreSQL: Long-term archive via periodic flush / lazy sync.
    - Auto Summarization: History diringkas otomatis saat threshold tercapai.
    """

    def __init__(self, session_id: str, flush_interval=60):
        self.session_id = session_id
        self.redis = ResilientRedisChatMessageHistory(session_id=session_id)
        self._pending_messages: list[BaseMessage] = []
        self._last_flush = time.time()
        self.flush_interval = flush_interval
        self._lock = threading.Lock()

    def _should_flush(self):
        return time.time() - self._last_flush > self.flush_interval

    @with_retry(max_retries=3)
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
                        session_id=self.session_id, role=role, content=msg.content
                    )
                    session.add(new_mem)
                session.commit()

            self._pending_messages.clear()
            self._last_flush = time.time()

            # Auto summarization check
            summarize_session(self.session_id)

    def add_message(self, message: BaseMessage) -> None:
        # Always add to Redis for instant access
        try:
            self.redis.add_message(message)
        except redis.RedisError:
            pass  # Graceful degrade - PG akan handle

        # Buffer message for Postgres
        with self._lock:
            self._pending_messages.append(message)

        # Flush if interval reached
        if self._should_flush():
            self._flush_to_postgres()

    @with_retry(max_retries=3)
    def clear(self) -> None:
        self._flush_to_postgres()
        try:
            self.redis.clear()
        except redis.RedisError:
            pass
        with SessionLocal() as session:
            session.execute(
                delete(SessionMemory).where(SessionMemory.session_id == self.session_id)
            )
            session.commit()
        self._pending_messages.clear()

    def force_summarize(self) -> str:
        """Paksa ringkas session sekarang. Return teks ringkasan, atau '' bila pesan belum cukup.

        Flush pending ke Postgres, ringkas via LLM, lalu rebuild cache Redis dari hasil
        ringkasan agar history lama di Redis tidak membayangi ringkasan baru.
        """
        self._flush_to_postgres()
        summarize_session(self.session_id)
        with SessionLocal() as session:
            stmt = (
                select(SessionMemory)
                .where(SessionMemory.session_id == self.session_id)
                .order_by(SessionMemory.timestamp)
            )
            rows = session.execute(stmt).scalars().all()
        try:
            self.redis.clear()
            for r in rows:
                if r.role == "assistant":
                    self.redis.add_message(AIMessage(content=r.content))
                elif r.role == "system":
                    self.redis.add_message(SystemMessage(content=r.content))
                else:
                    self.redis.add_message(HumanMessage(content=r.content))
        except redis.RedisError:
            pass
        with self._lock:
            self._pending_messages.clear()
        for r in rows:
            if r.role == "system" and r.content.startswith("RINGKASAN"):
                return r.content
        return ""

    @property
    def messages(self) -> list[BaseMessage]:
        # Check Redis first
        try:
            redis_msgs = self.redis.messages
            if redis_msgs:
                return redis_msgs
        except redis.RedisError:
            pass

        # Fallback to Postgres
        with SessionLocal() as session:
            stmt = (
                select(SessionMemory)
                .where(SessionMemory.session_id == self.session_id)
                .order_by(SessionMemory.timestamp)
            )
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
                try:
                    self.redis.add_message(m)
                except redis.RedisError:
                    pass
            return msgs
