from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
import time
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Optimasi Connection Pooling
# pool_size: Jumlah koneksi tetap di pool
# max_overflow: Jumlah koneksi ekstra yang bisa dibuat saat peak load
# pool_pre_ping: Mengecek koneksi masih hidup sebelum digunakan (mencegah error idle connection)
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800  # Recycle koneksi setiap 30 menit
)

def get_engine():
    return engine

# Event listeners untuk monitoring query performance
@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(time.time())
    # print(f"START QUERY: {statement[:100]}")

@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start = conn.info['query_start_time'].pop(-1)
    duration = time.time() - start
    if duration > 0.5:  # Warning untuk query > 500ms
        print(f"⚠️ SLOW QUERY [{duration:.3f}s]: {statement[:200]}")
