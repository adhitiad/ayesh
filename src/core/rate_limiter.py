"""Token bucket rate limiter per session."""

import time
import threading
from collections import defaultdict


class TokenBucket:
    """Token bucket rate limiter per session."""

    def __init__(self, capacity: int = 1, refill_per_sec: float = 0.33):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._buckets: dict[str, float] = defaultdict(lambda: float(capacity))
        self._timestamps: dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, session_id: str) -> float:
        with self._lock:
            now = time.time()
            last = self._timestamps.get(session_id, now)
            elapsed = now - last
            tokens = min(
                self.capacity,
                self._buckets[session_id] + elapsed * self.refill_per_sec,
            )
            if tokens >= 1.0:
                self._buckets[session_id] = tokens - 1.0
                self._timestamps[session_id] = now
                return 0.0
            wait = (1.0 - tokens) / self.refill_per_sec
            self._buckets[session_id] = 0.0
            self._timestamps[session_id] = now + wait
            return wait
