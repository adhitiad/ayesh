"""Pengelola memori percakapan Hybrid Optimized (Redis + PostgreSQL)."""

from dotenv import load_dotenv
from memory.optimized_hybrid import OptimizedHybridMemory

load_dotenv()

def get_memory_for_session(session_id: str):
    """Ambil memori sinkron antara Redis (Cache) dan PostgreSQL (Archive) dengan flush periodik."""
    return OptimizedHybridMemory(session_id=session_id)
