"""Redis-backed rate limiter with burst + sustained limits.

P2.1 — Replaces in-memory defaultdict with Redis for multi-worker support.
Keys: rate:{scope}:{identity}:{route}
Uses sliding window + token bucket hybrid with TTL.

Rate limits (per IP):
- /chat, /chat/stream, /chat/stream/tokens: burst=10/s, sustained=30/min
- /tasks, /jobs, /approvals, /feedback: burst=5/s, sustained=20/min
- /users: burst=2/s, sustained=5/min
"""

import os
import time

_REDIS_CLIENT = None
_redis_fallback_count = 0


def _get_redis():
    """Get or create Redis client (lazy init)."""
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    try:
        import redis as _redis_mod

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _REDIS_CLIENT = _redis_mod.from_url(
            url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
        )
        _REDIS_CLIENT.ping()
        return _REDIS_CLIENT
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("Redis rate limit init fail-open: %s", _e)
        return None


# === Rate limit configurations ===
# (burst_per_sec, sustained_per_min)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "chat": (10, 30),
    "tasks": (5, 20),
    "jobs": (5, 20),
    "approvals": (5, 20),
    "feedback": (5, 20),
    "users": (2, 5),
    "default": (5, 20),
}

# Path → scope mapping
_PATH_SCOPES: dict[str, str] = {
    "/chat": "chat",
    "/chat/stream": "chat",
    "/chat/stream/tokens": "chat",
    "/tasks": "tasks",
    "/jobs": "jobs",
    "/approvals": "approvals",
    "/feedback": "feedback",
    "/users": "users",
    "/users/bootstrap": "users",
}


def _scope_for_path(path: str) -> str | None:
    """Return rate limit scope for a path, or None if not rate-limited."""
    for prefix, scope in _PATH_SCOPES.items():
        if path == prefix or path.startswith(prefix + "/"):
            return scope
    return None


def check_rate_limit(
    scope: str, identity: str, burst: int | None = None, sustained: int | None = None
) -> tuple[bool, dict]:
    """Check rate limit using Redis sliding window.

    Args:
        scope: Rate limit scope (e.g. "chat", "users")
        identity: Client identity (e.g. IP address)
        burst: Override burst limit (per second)
        sustained: Override sustained limit (per minute)

    Returns:
        (allowed, info) where info contains limit, remaining, retry_after
    """
    burst_limit, sustained_limit = RATE_LIMITS.get(scope, RATE_LIMITS["default"])
    if burst is not None:
        burst_limit = burst
    if sustained is not None:
        sustained_limit = sustained

    r = _get_redis()
    if r is None:
        # Redis unavailable — fail-open for availability (rate limiting is defense-in-depth)
        global _redis_fallback_count
        _redis_fallback_count += 1
        return True, {
            "limit": sustained_limit,
            "remaining": sustained_limit,
            "retry_after": 0,
        }

    now = time.time()
    pipe = r.pipeline()
    key_burst = f"rate:{scope}:{identity}:burst"
    key_sustained = f"rate:{scope}:{identity}:sustained"

    # Burst: sliding window 1 second
    pipe.zremrangebyscore(key_burst, 0, now - 1)
    pipe.zadd(key_burst, {str(now): now})
    pipe.zcard(key_burst)
    pipe.expire(key_burst, 2)

    # Sustained: sliding window 60 seconds
    pipe.zremrangebyscore(key_sustained, 0, now - 60)
    pipe.zadd(key_sustained, {str(now): now})
    pipe.zcard(key_sustained)
    pipe.expire(key_sustained, 62)

    results = pipe.execute()
    burst_count = results[2]
    sustained_count = results[5]

    if burst_count > burst_limit:
        retry_after = 1
        return False, {
            "limit": sustained_limit,
            "remaining": 0,
            "retry_after": retry_after,
            "reason": "burst",
        }

    if sustained_count > sustained_limit:
        retry_after = 60 - (now - (results[4][0] if results[4] else now))
        return False, {
            "limit": sustained_limit,
            "remaining": 0,
            "retry_after": max(1, int(retry_after) + 1),
            "reason": "sustained",
        }

    return True, {
        "limit": sustained_limit,
        "remaining": max(0, sustained_limit - sustained_count),
        "retry_after": 0,
    }
