"""Redis Patch: Force RESP2 protocol untuk kompatibilitas dengan Redis server lama."""

import redis


def apply_redis_patch():
    """Patch redis.from_url untuk menggunakan protocol=2 (RESP2)."""
    _original_from_url = redis.from_url

    def _patched_from_url(url, **kwargs):
        kwargs.setdefault("protocol", 2)
        return _original_from_url(url, **kwargs)

    redis.from_url = _patched_from_url
