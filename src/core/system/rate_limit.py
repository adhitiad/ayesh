"""Redis-backed rate limiter with burst + sustained limits.

Keys: rate:{scope}:{kind}:{identity}:{route}
Identitas ganda:
- kind="ip": per IP (siapa pun, termasuk anonim).
- kind="user": per user terautentikasi (role-aware: vip dapat limit lebih longgar).

Rate limits (per scope, per-IP default):
- chat: burst=10/s, sustained=30/min  (vip: 20/s, 120/min bila VIP env tidak di-override)
- tasks/jobs/approvals/feedback: burst=5/s, sustained=20/min (vip: 10/s, 60/min)
- users: burst=2/s, sustained=5/min
- register: burst=2/s, sustained=5/min (IP only)
- webhooks: burst=5/s, sustained=20/min

Env:
- RATE_LIMIT_{SCOPE}_BURST / SUSTAINED (per IP)
- RATE_LIMIT_{SCOPE}_USER_BURST / USER_SUSTAINED (per user, default = per IP)
- RATE_LIMIT_{SCOPE}_VIP_BURST / VIP_SUSTAINED (per vip, default = user*2 / user*4)
"""

import os
import threading
import time

_REDIS_CLIENT = None
_redis_fallback_count = 0


# === In-memory fallback rate limiter (used when Redis unavailable) ===
class _InMemoryRateLimiter:
    """Sliding window rate limiter using in-memory dicts.

    Not shared across processes/workers, but better than no rate limiting.
    Auto-cleans old entries every 60 seconds.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._windows: dict[str, list[float]] = {}
        self._last_cleanup = time.time()

    def _cleanup(self):
        now = time.time()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        cutoff = now - 120
        stale = [k for k, v in self._windows.items() if not v or v[-1] < cutoff]
        for k in stale:
            del self._windows[k]

    def check(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        """Check if request is allowed within window.

        Returns (allowed, count). count is current requests in window.
        """
        now = time.time()
        with self._lock:
            self._cleanup()
            cutoff = now - window
            entries = self._windows.setdefault(key, [])
            # Remove entries outside window
            while entries and entries[0] < cutoff:
                entries.pop(0)
            count = len(entries)
            if count >= limit:
                return False, count
            entries.append(now)
            return True, count + 1


_IN_MEMORY = _InMemoryRateLimiter()


def _get_redis():
    """Get or create Redis client (lazy init)."""
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    try:
        import redis as _redis_mod

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _REDIS_CLIENT = _redis_mod.from_url(url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
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
    "register": (2, 5),
    "webhooks": (5, 20),
    "health": (10, 30),
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
    "/users/register": "register",
    "/webhooks": "webhooks",
    "/webhooks/vip-upgrade": "webhooks",
    "/users": "users",
    "/users/bootstrap": "users",
    "/health": "health",
    "/metrics": "health",
}


# Env var overrides: RATE_LIMIT_{SCOPE}_BURST, RATE_LIMIT_{SCOPE}_SUSTAINED
def _load_env_limits() -> dict[str, tuple[int, int]]:
    """Load rate limit overrides from environment variables."""
    limits = dict(RATE_LIMITS)
    for scope in list(RATE_LIMITS.keys()):
        burst_env = os.getenv(f"RATE_LIMIT_{scope.upper()}_BURST")
        sustained_env = os.getenv(f"RATE_LIMIT_{scope.upper()}_SUSTAINED")
        if burst_env is not None:
            limits[scope] = (int(burst_env), limits[scope][1])
        if sustained_env is not None:
            limits[scope] = (limits[scope][0], int(sustained_env))
    return limits


def _user_limits(scope: str) -> tuple[int, int]:
    """Per-user limits: default = per-scope, bisa di-override RATE_LIMIT_{SCOPE}_USER_*."""
    burst, sustained = _load_env_limits().get(scope, RATE_LIMITS["default"])
    user_burst = os.getenv(f"RATE_LIMIT_{scope.upper()}_USER_BURST")
    user_sustained = os.getenv(f"RATE_LIMIT_{scope.upper()}_USER_SUSTAINED")
    if user_burst is not None:
        burst = int(user_burst)
    if user_sustained is not None:
        sustained = int(user_sustained)
    return burst, sustained


def _vip_limits(scope: str) -> tuple[int, int]:
    """Per-vip limits: default = user*2 burst, user*4 sustained, bisa di-override VIP_*."""
    burst, sustained = _user_limits(scope)
    vip_burst = os.getenv(f"RATE_LIMIT_{scope.upper()}_VIP_BURST")
    vip_sustained = os.getenv(f"RATE_LIMIT_{scope.upper()}_VIP_SUSTAINED")
    burst = int(vip_burst) if vip_burst is not None else burst * 2
    if vip_sustained is not None:
        sustained = int(vip_sustained)
    else:
        sustained = sustained * 4 if scope in ("chat", "tasks", "jobs", "approvals", "feedback") else sustained * 2
    return burst, sustained


def get_limits_for_role(scope: str, role: str | None) -> tuple[int, int]:
    """Return burst/sustained untuk role tertentu (vip vs user)."""
    if role == "vip" or role == "owner":
        return _vip_limits(scope)
    return _user_limits(scope)


def _scope_for_path(path: str) -> str | None:
    """Return rate limit scope for a path, or None if not rate-limited."""
    for prefix, scope in _PATH_SCOPES.items():
        if path == prefix or path.startswith(prefix + "/"):
            return scope
    return None


def check_rate_limit(
    scope: str,
    identity: str,
    burst: int | None = None,
    sustained: int | None = None,
    kind: str = "ip",
    role: str | None = None,
) -> tuple[bool, dict]:
    """Check rate limit using Redis sliding window."""
    if kind == "user":
        burst_limit, sustained_limit = get_limits_for_role(scope, role)
    else:
        limits = _load_env_limits()
        burst_limit, sustained_limit = limits.get(scope, limits["default"])
    if burst is not None:
        burst_limit = burst
    if sustained is not None:
        sustained_limit = sustained

    r = _get_redis()
    if r is None:
        # Redis unavailable — fallback to in-memory rate limiter
        global _redis_fallback_count
        _redis_fallback_count += 1

        # Burst check (1 second window)
        burst_key = f"mem:{scope}:{kind}:{identity}:burst"
        burst_allowed, burst_count = _IN_MEMORY.check(burst_key, burst_limit, 1.0)
        if not burst_allowed:
            return False, {
                "limit": sustained_limit,
                "remaining": 0,
                "retry_after": 1,
                "reason": "burst_in_memory",
            }

        # Sustained check (60 second window)
        sustained_key = f"mem:{scope}:{kind}:{identity}:sustained"
        sustained_allowed, sustained_count = _IN_MEMORY.check(sustained_key, sustained_limit, 60.0)
        if not sustained_allowed:
            return False, {
                "limit": sustained_limit,
                "remaining": 0,
                "retry_after": 60,
                "reason": "sustained_in_memory",
            }

        return True, {
            "limit": sustained_limit,
            "remaining": max(0, sustained_limit - sustained_count),
            "retry_after": 0,
            "fallback": True,
        }

    now = time.time()
    pipe = r.pipeline()
    key_burst = f"rate:{scope}:{kind}:{identity}:burst"
    key_sustained = f"rate:{scope}:{kind}:{identity}:sustained"

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
        retry_after: float = 1
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
