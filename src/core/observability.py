import time
from dataclasses import dataclass
from typing import Dict
from sqlalchemy import text
from src.core.db_engine import get_engine
from dotenv import load_dotenv
import os
import redis

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

engine = get_engine()

# In-memory metrics store
metrics: Dict[str, float] = {}

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
    try:
        start = time.time()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status.postgres = True
        status.db_latency_ms = (time.time() - start) * 1000
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("health_check postgres error: %s", _e)
        status.postgres = False

    try:
        start = time.time()
        redis_client.ping()
        status.redis = True
        status.redis_latency_ms = (time.time() - start) * 1000
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("health_check redis error: %s", _e)
        status.redis = False

    return status


def get_metrics() -> Dict:
    return {
        "postgres_healthy": health_check().postgres,
        "redis_healthy": health_check().redis,
        "last_query_ms": metrics.get("last_query_ms", 0),
    }
