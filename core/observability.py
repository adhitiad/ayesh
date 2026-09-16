import time
from dataclasses import dataclass
from typing import Dict
from sqlalchemy import create_engine, text
from sqlalchemy import event
from dotenv import load_dotenv
import os
import redis

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# In-memory metrics store
metrics: Dict[str, float] = {}

def _record_query_timing(engine):
    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault('query_start_time', []).append(time.time())
    
    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        start = conn.info['query_start_time'].pop(-1)
        duration = time.time() - start
        metrics['last_query_ms'] = duration * 1000
        if duration > 0.5:
            print(f"[SLOW QUERY] {duration:.3f}s - {statement[:150]}")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
_record_query_timing(engine)

# Redis persistent pool
redis_pool = redis.ConnectionPool.from_url(REDIS_URL, protocol=2, max_connections=10)
redis_client = redis.Redis(connection_pool=redis_pool)

@dataclass
class HealthStatus:
    postgres: bool = False
    redis: bool = False
    db_latency_ms: float = -1
    redis_latency_ms: float = -1

def health_check() -> HealthStatus:
    status = HealthStatus()
    # Check Postgres
    try:
        start = time.time()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status.postgres = True
        status.db_latency_ms = (time.time() - start) * 1000
    except Exception as e:
        status.postgres = False
    
    # Check Redis
    try:
        start = time.time()
        redis_client.ping()
        status.redis = True
        status.redis_latency_ms = (time.time() - start) * 1000
    except Exception:
        status.redis = False
    
    return status

def get_metrics() -> Dict:
    return {
        "postgres_healthy": health_check().postgres,
        "redis_healthy": health_check().redis,
        "last_query_ms": metrics.get('last_query_ms', 0)
    }

