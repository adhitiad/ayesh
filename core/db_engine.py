from sqlalchemy import create_engine, event
from sqlalchemy.pool import QueuePool
import time
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL belum diatur di .env. "
        "Salin .env.example ke .env dan isi nilai DATABASE_URL."
    )

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=30,
)

def get_engine():
    return engine

# Event listeners instance-level (satu listener, tidak dobel)
@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(time.time())

@event.listens_for(engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start = conn.info['query_start_time'].pop(-1)
    duration = time.time() - start
    if duration > 0.5:
        print(f"⚠️ SLOW QUERY [{duration:.3f}s]: {statement[:200]}")


def with_retry(max_retries=3, base_delay=0.5, max_delay=5.0):
    """Decorator untuk retry dengan exponential backoff pada query DB."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        time.sleep(delay)
                        continue
                    raise
            raise last_error
        return wrapper
    return decorator
