"""FASE 1 — Rate limit per-user (Redis-backed).

Bucket terpisah per identitas: kind="ip" (per-IP, selalu) dan kind="user"
(per user bila API key valid). Dua bucket dihitung terpisah; yang lebih ketat
berlaku. Redis yang absent → fail-open (rate limiting adalah defense-in-depth,
bukan authorization boundary).

Test cepat, tanpa Redis/LLM/infra: pakai FakeRedis untuk memeriksa struktur key
& alur keputusan secara deterministik.
"""

import os
import unittest
from unittest import mock


class _FakeRedisClient:
    """Redis minimal: pipeline direkam, zcard = jumlah zadd pada key yang sama."""

    def __init__(self):
        self.queue = []

    def ping(self):
        return True

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, client):
        self.client = client
        self.queue = client.queue

    def zremrangebyscore(self, key, *_args):
        self.queue.append(("zrem", key))
        return self

    def zadd(self, key, *_args, **_kwargs):
        self.queue.append(("zadd", key))
        return self

    def zcard(self, key):
        self.queue.append(("zcard", key))
        return self

    def expire(self, key, _ttl):
        self.queue.append(("expire", key))
        return self

    def _count(self, key):
        return sum(1 for op, k in self.queue if op == "zadd" and k == key)

    def execute(self):
        out = []
        for op, key in self.queue:
            if op == "zcard":
                out.append(self._count(key))
            elif op == "zadd":
                out.append(1)
            elif op == "zrem":
                out.append(0)
            else:
                out.append(True)
        return out


class TestRateLimitKeys(unittest.TestCase):
    """Struktur key Redis: {scope}:{kind}:{identity}. Kind menentukan bucket."""

    def _patched_redis(self):
        client = _FakeRedisClient()
        patcher = mock.patch("src.core.system.rate_limit._get_redis", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def test_default_kind_is_ip(self):
        """Tanpa argumen kind, bucket dinilai per-IP."""
        client = self._patched_redis()
        from src.core.system.rate_limit import check_rate_limit

        allowed, info = check_rate_limit("chat", "1.2.3.4")
        self.assertTrue(allowed)
        keys = {k for _op, k in client.queue}
        self.assertIn("rate:chat:ip:1.2.3.4:burst", keys)
        self.assertIn("rate:chat:ip:1.2.3.4:sustained", keys)
        self.assertIn("limit", info)
        self.assertIn("remaining", info)

    def test_user_kind_uses_separate_bucket(self):
        """kind='user' memakai key terpisah dari per-IP."""
        client = self._patched_redis()
        from src.core.system.rate_limit import check_rate_limit

        allowed, _ = check_rate_limit("chat", "user-abc", kind="user")
        self.assertTrue(allowed)
        keys = {k for _op, k in client.queue}
        self.assertIn("rate:chat:user:user-abc:burst", keys)
        self.assertIn("rate:chat:user:user-abc:sustained", keys)
        self.assertNotIn("rate:chat:ip:user-abc:burst", keys)

    def test_ip_and_user_are_isolated(self):
        """IP yang sama + user berbeda tidak berbagi bucket."""
        from src.core.system.rate_limit import check_rate_limit

        ip_client = _FakeRedisClient()
        user_client = _FakeRedisClient()
        with mock.patch("src.core.system.rate_limit._get_redis", return_value=ip_client):
            check_rate_limit("chat", "10.0.0.1", kind="ip")
        with mock.patch("src.core.system.rate_limit._get_redis", return_value=user_client):
            check_rate_limit("chat", "u-1", kind="user")
        ip_keys = {k for _op, k in ip_client.queue}
        user_keys = {k for _op, k in user_client.queue}
        self.assertNotIn("rate:chat:user:u-1:burst", ip_keys)
        self.assertNotIn("rate:chat:ip:10.0.0.1:burst", user_keys)

    def test_burst_denied_when_overridden(self):
        """Limit burst=0 → request deny dengan reason 'burst'."""
        client = self._patched_redis()
        from src.core.system.rate_limit import check_rate_limit

        allowed, info = check_rate_limit("chat", "u-2", burst=0, kind="user")
        self.assertFalse(allowed)
        self.assertEqual(info["reason"], "burst")
        self.assertEqual(info["remaining"], 0)
        self.assertGreaterEqual(info["retry_after"], 1)
        # Key tetap memakai bucket user
        keys = {k for _op, k in client.queue}
        self.assertIn("rate:chat:user:u-2:burst", keys)


class TestUserLimitsEnv(unittest.TestCase):
    """Env override per-user RATE_LIMIT_{SCOPE}_USER_* (default = per-IP)."""

    ENV_VARS = ("RATE_LIMIT_CHAT_USER_BURST", "RATE_LIMIT_CHAT_USER_SUSTAINED")

    def setUp(self):
        self._saved = {v: os.environ.pop(v, None) for v in self.ENV_VARS}

    def tearDown(self):
        for v, old in self._saved.items():
            if old is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = old

    def test_defaults_follow_base_limits(self):
        from src.core.system.rate_limit import RATE_LIMITS, _user_limits

        self.assertEqual(_user_limits("chat"), RATE_LIMITS["chat"])

    def test_override_env(self):
        from src.core.system.rate_limit import _user_limits

        os.environ["RATE_LIMIT_CHAT_USER_BURST"] = "3"
        os.environ["RATE_LIMIT_CHAT_USER_SUSTAINED"] = "7"
        self.assertEqual(_user_limits("chat"), (3, 7))


class TestRedisFailOpen(unittest.TestCase):
    """Redis tidak tersedia → fail-open (allow), rate limiting defense-in-depth."""

    def test_allowed_when_redis_down(self):
        from src.core.system.rate_limit import check_rate_limit

        with mock.patch("src.core.system.rate_limit._get_redis", return_value=None):
            allowed, info = check_rate_limit("chat", "x", kind="user")
        self.assertTrue(allowed)
        self.assertIn("limit", info)
        self.assertIn("remaining", info)


class TestAuthedUserId(unittest.TestCase):
    """Resolusi user id di middleware: key valid → id; selainnya None."""

    def _req(self, headers=None):
        return type("FakeRequest", (), {"headers": headers or {}})()

    def test_valid_key_returns_id(self):
        from src.api.middleware import _authed_user_id

        with mock.patch("src.api.middleware.verify_key", return_value={"id": "u-9", "role": "user"}):
            rid = _authed_user_id(self._req({"X-API-Key": "fr_abcdef"}))
        self.assertEqual(rid, "u-9")

    def test_bearer_returns_id(self):
        from src.api.middleware import _authed_user_id

        with mock.patch("src.api.middleware.verify_key", return_value={"id": "u-1"}):
            rid = _authed_user_id(self._req({"Authorization": "Bearer fr_xyz"}))
        self.assertEqual(rid, "u-1")

    def test_no_key_returns_none(self):
        from src.api.middleware import _authed_user_id

        rid = _authed_user_id(self._req({}))
        self.assertIsNone(rid)

    def test_invalid_key_returns_none(self):
        from src.api.middleware import _authed_user_id

        with mock.patch("src.api.middleware.verify_key", return_value=None):
            rid = _authed_user_id(self._req({"X-API-Key": "fr_wrong"}))
        self.assertIsNone(rid)

    def test_lookup_error_returns_none(self):
        """Kegagalan DB di middleware tidak boleh jadi 500 — jatuh ke bucket IP."""
        from src.api.middleware import _authed_user_id

        with mock.patch("src.api.middleware.verify_key", side_effect=RuntimeError("db down")):
            rid = _authed_user_id(self._req({"X-API-Key": "fr_abc"}))
        self.assertIsNone(rid)


if __name__ == "__main__":
    unittest.main()
