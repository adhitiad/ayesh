"""Test sesi (auth_sessions) + helper cookie/CSRF double-submit.

Butuh DB (Postgres) dan auth_tables di-lazy-ensure. Menggunakan user nyata via
create_user; baris sesi dihapus di tearDown.
"""

import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from src.core.auth.sessions import (
    SESSION_COOKIE_NAME,
    clear_session_cookies,
    create_session,
    read_session_token,
    revoke_all_user_sessions,
    revoke_session,
    set_session_cookie,
    verify_csrf,
    verify_session,
)
from src.core.db.db_engine import get_session
from src.core.db.models import AuthSession, User

_ENV = patch.dict(
    os.environ,
    {
        "AUTH_SESSION_TTL_HOURS": "2",
        "AUTH_COOKIE_SECURE": "0",
        "AUTH_COOKIE_SAMESITE": "lax",
    },
)


def setUpModule():
    _ENV.start()


def tearDownModule():
    _ENV.stop()
    with get_session() as db:
        db.query(AuthSession).delete()
        db.commit()


class TestSessionLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.uid = str(uuid.uuid4())
        with get_session() as db:
            db.add(
                User(
                    id=cls.uid,
                    name="sesi-test",
                    key_hash=f"h{cls.uid}",
                    prefix=f"fr_{cls.uid[:6]}",
                    role="user",
                    active=True,
                )
            )
            db.commit()

    def test_create_verify_revoke(self):
        info = create_session(self.uid, ip="1.2.3.4", user_agent="pytest")
        self.assertTrue(info["session_token"].startswith("ayss_"))
        verified = verify_session(info["session_token"])
        self.assertIsNotNone(verified)
        self.assertEqual(verified["user_id"], self.uid)
        self.assertTrue(revoke_session(info["session_token"]))
        self.assertIsNone(verify_session(info["session_token"]))

    def test_verify_unknown_token(self):
        info = create_session(self.uid)
        verified = verify_session(info["session_token"] + "x")
        self.assertIsNone(verified)
        self.assertIsNone(verify_session(None))
        self.assertIsNone(verify_session(""))

    def test_revoke_all_keeps_current(self):
        a = create_session(self.uid)
        b = create_session(self.uid)
        c = create_session(self.uid)
        count = revoke_all_user_sessions(self.uid, keep_token=b["session_token"])
        self.assertEqual(count, 2)
        self.assertIsNotNone(verify_session(b["session_token"]))
        self.assertIsNone(verify_session(a["session_token"]))
        self.assertIsNone(verify_session(c["session_token"]))

    def test_revoke_already_revoked_false(self):
        info = create_session(self.uid)
        self.assertTrue(revoke_session(info["session_token"]))
        self.assertFalse(revoke_session(info["session_token"]))


class TestCookieHelpers(unittest.TestCase):
    def _fake_request(self, cookies=None, headers=None):
        return SimpleNamespace(cookies=cookies or {}, headers=headers or {})

    def test_read_session_token(self):
        req = self._fake_request(cookies={SESSION_COOKIE_NAME: " ayss_x "})
        self.assertEqual(read_session_token(req), "ayss_x")
        req2 = self._fake_request(cookies={})
        self.assertIsNone(read_session_token(req2))

    def test_set_and_clear(self):
        from types import SimpleNamespace as NS

        resp = NS()
        resp.set_cookie = lambda *a, **k: setattr(resp, "_cookies", [*getattr(resp, "_cookies", []), (a, k)])
        resp.delete_cookie = lambda *a, **k: setattr(resp, "_deleted", [*getattr(resp, "_deleted", []), (a, k)])
        set_session_cookie(resp, "ayss_test")
        names = [a[0] for a, _ in resp._cookies]
        self.assertIn(SESSION_COOKIE_NAME, names)
        self.assertIn("ayesh_csrf", names)
        sess = next((a, k) for a, k in resp._cookies if a[0] == SESSION_COOKIE_NAME)
        args, attrs = sess
        self.assertEqual(args[1], "ayss_test")
        self.assertTrue(attrs["httponly"])
        self.assertFalse(attrs["secure"])
        self.assertEqual(attrs["samesite"], "lax")
        clear_session_cookies(resp)
        self.assertIn(SESSION_COOKIE_NAME, [a[0] for a, _ in resp._deleted])

    def test_verify_csrf_double_submit(self):
        req = self._fake_request(cookies={"ayesh_csrf": "tok123"}, headers={"X-CSRF-Token": "tok123"})
        self.assertTrue(verify_csrf(req))
        req2 = self._fake_request(cookies={"ayesh_csrf": "tok123"}, headers={"X-CSRF-Token": "tok456"})
        self.assertFalse(verify_csrf(req2))
        req3 = self._fake_request(cookies={}, headers={"X-CSRF-Token": "tok123"})
        self.assertFalse(verify_csrf(req3))
        req4 = self._fake_request(cookies={"ayesh_csrf": "tok123"}, headers={})
        self.assertFalse(verify_csrf(req4))


if __name__ == "__main__":
    unittest.main()
