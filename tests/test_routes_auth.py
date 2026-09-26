"""Test endpoint /auth (register/login/me/logout/2FA/CSRF) via TestClient.

Butuh DB + (opsional) Redis (rate limit). Rate limit auth di-longgarkan agar
test 2FA/CSRF tidak flaky. Baris user/auth dibersihkan di tearDown.
"""

import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pyotp
from fastapi.testclient import TestClient

from api_server import app
from src.core.db.db_engine import get_session
from src.core.db.models import AuthOAuthAccount, AuthSession, AuthToken, User
from src.core.system.rate_limit import _scope_for_path, check_rate_limit

_KNOWN_UIDS: list[str] = []
_PW = "secret-pass-123"

_ENV = patch.dict(
    os.environ,
    {
        "AUTH_DEV_VERIFY": "1",
        "AUTH_REQUIRE_EMAIL_VERIFICATION": "1",
        "RATE_LIMIT_AUTH_BURST": "500",
        "RATE_LIMIT_AUTH_SUSTAINED": "10000",
        "RATE_LIMIT_AUTH_USER_BURST": "500",
        "RATE_LIMIT_AUTH_USER_SUSTAINED": "10000",
        "AUTH_OAUTH_GOOGLE_CLIENT_ID": "",
        "AUTH_OAUTH_GOOGLE_CLIENT_SECRET": "",
    },
)


def setUpModule():
    _ENV.start()


def tearDownModule():
    _ENV.stop()
    with get_session() as db:
        db.query(AuthOAuthAccount).filter(AuthOAuthAccount.user_id.in_(_KNOWN_UIDS)).delete(synchronize_session=False)
        db.query(AuthSession).filter(AuthSession.user_id.in_(_KNOWN_UIDS)).delete(synchronize_session=False)
        db.query(AuthToken).filter(AuthToken.user_id.in_(_KNOWN_UIDS)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(_KNOWN_UIDS)).delete(synchronize_session=False)
        db.commit()


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _email() -> str:
    return f"rt{uuid.uuid4().hex[:12]}@test.local"


def _register_verified(
    client: TestClient, email: str, password: str | None = None, username: str | None = None
) -> dict:
    password = password or _PW
    payload: dict = {"email": email, "password": password, "name": "RouteTest"}
    if username is not None:
        payload["username"] = username
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    account = resp.json()["account"]
    _KNOWN_UIDS.append(account["id"])
    dev_link = resp.json()["dev_link"]
    token = dev_link.rsplit("token=", 1)[1]
    r = client.post("/auth/email/verify", json={"token": token})
    assert r.status_code == 200, r.text
    return account


# --- helper OAuth success path (mock httpx) ---------------------------------

_OAUTH_ENABLED_ENV = {
    "AUTH_OAUTH_GOOGLE_CLIENT_ID": "gid-unit",
    "AUTH_OAUTH_GOOGLE_CLIENT_SECRET": "gsec-unit",
}


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Pengganti httpx.AsyncClient: POST /token → access_token, GET userinfo → `userinfo`."""

    userinfo: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        return _FakeResp({"access_token": "unit-token"})

    async def get(self, *args, **kwargs):
        return _FakeResp(type(self).userinfo)


def _oauth_state(client: TestClient, provider: str = "google") -> str:
    """Mulai OAuth via route → state asli yang tersimpan di auth_oauth_states."""
    resp = client.get(f"/auth/oauth/{provider}", follow_redirects=False)
    assert resp.status_code == 302, resp.text
    query = parse_qs(urlparse(resp.headers["location"]).query)
    assert "state" in query, resp.headers["location"]
    return query["state"][0]


class TestRegisterLoginMeLogout(unittest.TestCase):
    def test_register_returns_verified_false(self):
        client = _client()
        email = _email()
        resp = client.post("/auth/register", json={"email": email, "password": "secret-pass-123", "name": "X"})
        self.assertEqual(resp.status_code, 201, resp.text)
        account = resp.json()["account"]
        _KNOWN_UIDS.append(account["id"])
        self.assertFalse(account["email_verified"])
        self.assertEqual(account["auth_provider"], "password")

    def test_login_me_logout(self):
        client = _client()
        email = _email()
        password = "secret-pass-123"
        _register_verified(client, email, password)
        # logout dulu untuk buang session register? register tidak bikin session.
        login = client.post("/auth/login", json={"email": email, "password": password})
        self.assertEqual(login.status_code, 200, login.text)
        data = login.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["account"]["email_verified"])
        self.assertIn("set-cookie", login.headers)
        self.assertIn("HttpOnly", login.headers["set-cookie"])

        me = client.get("/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["email"], email)

        out = client.post("/auth/logout", headers={"X-CSRF-Token": client.cookies.get("ayesh_csrf")})
        self.assertEqual(out.status_code, 200, out.text)
        me2 = client.get("/auth/me")
        self.assertEqual(me2.status_code, 401, me2.text)

    def test_login_unverified_blocked(self):
        client = _client()
        email = _email()
        password = "secret-pass-123"
        resp = client.post("/auth/register", json={"email": email, "password": password, "name": "X"})
        self.assertEqual(resp.status_code, 201, resp.text)
        _KNOWN_UIDS.append(resp.json()["account"]["id"])
        login = client.post("/auth/login", json={"email": email, "password": password})
        self.assertEqual(login.status_code, 403, login.text)
        self.assertEqual(login.json()["detail"], "Email belum diverifikasi. Cek email atau minta ulang token.")

    def test_login_wrong_credentials(self):
        client = _client()
        login = client.post("/auth/login", json={"email": "nobody@test.local", "password": "whatever-123"})
        self.assertEqual(login.status_code, 401, login.text)

    def test_verify_token_one_time_via_route(self):
        client = _client()
        email = _email()
        resp = client.post("/auth/register", json={"email": email, "password": "secret-pass-123", "name": "X"})
        account = resp.json()["account"]
        _KNOWN_UIDS.append(account["id"])
        token = resp.json()["dev_link"].rsplit("token=", 1)[1]
        ok = client.post("/auth/email/verify", json={"token": token})
        self.assertEqual(ok.status_code, 200)
        again = client.post("/auth/email/verify", json={"token": token})
        self.assertEqual(again.status_code, 400)


class TestCsrfProtection(unittest.TestCase):
    def setUp(self):
        self.client = _client()
        self.email = _email()
        _register_verified(self.client, self.email, "secret-pass-123")
        login = self.client.post("/auth/login", json={"email": self.email, "password": "secret-pass-123"})
        self.assertEqual(login.status_code, 200)
        self.csrf = self.client.cookies.get("ayesh_csrf")

    def test_mutation_requires_csrf_token(self):
        resp = self.client.post(
            "/auth/password/change",
            json={"current_password": "secret-pass-123", "new_password": "new-pass-456"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "csrf_token")

    def test_bad_origin_rejected(self):
        resp = self.client.post(
            "/auth/password/change",
            json={"current_password": "secret-pass-123", "new_password": "new-pass-456"},
            headers={"X-CSRF-Token": self.csrf, "Origin": "http://evil.example"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "csrf_origin")

    def test_valid_csrf_passes(self):
        resp = self.client.post(
            "/auth/password/change",
            json={"current_password": "secret-pass-123", "new_password": "new-pass-456"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        # password lama sudah tidak valid (cek dari client bersih tanpa session)
        old = _client().post("/auth/login", json={"email": self.email, "password": "secret-pass-123"})
        self.assertEqual(old.status_code, 401)

    def test_logout_requires_csrf(self):
        resp = self.client.post("/auth/logout")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "csrf_token")

    def test_logout_with_csrf_ok(self):
        resp = self.client.post("/auth/logout", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(resp.status_code, 200, resp.text)


class TestTwoFactorRoutes(unittest.TestCase):
    def setUp(self):
        self.client = _client()
        self.email = _email()
        _register_verified(self.client, self.email, "secret-pass-123")
        login = self.client.post("/auth/login", json={"email": self.email, "password": "secret-pass-123"})
        self.assertEqual(login.status_code, 200)
        self.csrf = self.client.cookies.get("ayesh_csrf")

    def test_enable_and_login_with_totp(self):
        setup = self.client.post("/auth/2fa/setup", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(setup.status_code, 200, setup.text)
        secret = setup.json()["secret"]
        code = pyotp.TOTP(secret).now()
        confirm = self.client.post("/auth/2fa/confirm", json={"code": code}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(confirm.status_code, 200, confirm.text)
        backup_codes = confirm.json()["backup_codes"]
        self.assertEqual(len(backup_codes), 10)
        self.assertRegex(backup_codes[0], r"^[0-9A-F]{4}-[0-9A-F]{4}$")

        # login ulang dari client bersih → 2fa_required
        fresh = _client()
        login = fresh.post("/auth/login", json={"email": self.email, "password": "secret-pass-123"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["status"], "2fa_required")
        challenge = login.json()["challenge"]
        code2 = pyotp.TOTP(secret).now()
        ok = fresh.post("/auth/login/2fa", json={"challenge": challenge, "code": code2})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["status"], "ok")
        me = fresh.get("/auth/me")
        self.assertEqual(me.status_code, 200)

        # disable via password
        disable = self.client.post(
            "/auth/2fa/disable",
            json={"password": "secret-pass-123"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(disable.status_code, 200, disable.text)
        fresh2 = _client()
        login_no2fa = fresh2.post("/auth/login", json={"email": self.email, "password": "secret-pass-123"})
        self.assertEqual(login_no2fa.json()["status"], "ok")


class TestOAuthRoutes(unittest.TestCase):
    def test_start_unknown_provider(self):
        client = _client()
        resp = client.get("/auth/oauth/bogus")
        self.assertEqual(resp.status_code, 400)

    def test_start_disabled_provider(self):
        client = _client()
        resp = client.get("/auth/oauth/google")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("tidak dikonfigurasi", resp.json()["detail"])

    def test_callback_missing_params(self):
        client = _client()
        resp = client.get("/auth/oauth/google/callback", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("reason=missing_params", resp.headers["location"])


class TestOAuthSuccessPath(unittest.TestCase):
    """Callback sukses dengan httpx mock: buat user + sesi cookie; kasus link akun lama."""

    def test_callback_creates_user_and_session(self):
        client = _client()
        email = _email()
        with (
            patch.dict(os.environ, _OAUTH_ENABLED_ENV),
            patch("src.core.auth.oauth.httpx.AsyncClient", _FakeAsyncClient),
        ):
            _FakeAsyncClient.userinfo = {
                "sub": f"g-{uuid.uuid4().hex[:8]}",
                "email": email,
                "email_verified": True,
                "name": "OAuth Baru",
            }
            state = _oauth_state(client)
            cb = client.get(
                f"/auth/oauth/google/callback?code=unit-code&state={state}",
                follow_redirects=False,
            )
        self.assertEqual(cb.status_code, 302, cb.text)
        self.assertIn("auth=ok", cb.headers["location"])
        self.assertTrue(any("ayesh_session=" in c for c in cb.headers.get_list("set-cookie")))

        with get_session() as db:
            row = db.query(User).filter(User.email == email).first()
            self.assertIsNotNone(row)
            _KNOWN_UIDS.append(str(row.id))
            self.assertTrue(row.email_verified)
            self.assertEqual(row.auth_provider, "google")
            self.assertEqual(row.oauth_provider_id, _FakeAsyncClient.userinfo["sub"])

        me = client.get("/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["email"], email)

    def test_callback_links_existing_account(self):
        client = _client()
        email = _email()
        _register_verified(client, email)
        login = client.post("/auth/login", json={"email": email, "password": _PW})
        self.assertEqual(login.status_code, 200, login.text)

        with (
            patch.dict(os.environ, _OAUTH_ENABLED_ENV),
            patch("src.core.auth.oauth.httpx.AsyncClient", _FakeAsyncClient),
        ):
            _FakeAsyncClient.userinfo = {
                "sub": "g-linked-1",
                "email": email,
                "email_verified": True,
                "name": "OAuth Link",
            }
            state = _oauth_state(client)
            cb = client.get(
                f"/auth/oauth/google/callback?code=unit-code&state={state}",
                follow_redirects=False,
            )
        self.assertEqual(cb.status_code, 302, cb.text)
        self.assertIn("auth=ok", cb.headers["location"])

        me = client.get("/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["email"], email)

        with get_session() as db:
            row = db.query(User).filter(User.email == email).first()
            self.assertIsNotNone(row)
            self.assertEqual(row.auth_provider, "google")
            self.assertEqual(row.oauth_provider_id, "g-linked-1")
            self.assertTrue(row.email_verified)


class TestRegisterEmailSendFailure(unittest.TestCase):
    """SMTP aktif: kirim email gagal → 503 fail-closed, akun tetap belum terverifikasi."""

    _SMTP_ENV = {
        "SMTP_ENABLED": "1",
        "SMTP_HOST": "smtp.test.local",
        "SMTP_USER": "unit@test.local",
        "SMTP_PASSWORD": "pw-unit",
        "SMTP_STARTTLS": "0",
    }

    def test_register_503_and_account_stays_unverified(self):
        client = _client()
        email = _email()
        with (
            patch.dict(os.environ, self._SMTP_ENV),
            patch(
                "src.api.routes_auth.send_email",
                new_callable=AsyncMock,
                side_effect=RuntimeError("smtp down"),
            ),
        ):
            resp = client.post("/auth/register", json={"email": email, "password": _PW, "name": "X"})
        self.assertEqual(resp.status_code, 503, resp.text)
        self.assertIn("email verifikasi gagal", resp.json()["detail"])

        with get_session() as db:
            row = db.query(User).filter(User.email == email).first()
            self.assertIsNotNone(row)
            _KNOWN_UIDS.append(str(row.id))
            self.assertFalse(row.email_verified)

        login = client.post("/auth/login", json={"email": email, "password": _PW})
        self.assertEqual(login.status_code, 403, login.text)

    def test_register_201_when_smtp_ok(self):
        client = _client()
        email = _email()
        mock_send = AsyncMock(return_value=True)
        with patch.dict(os.environ, self._SMTP_ENV), patch("src.api.routes_auth.send_email", new=mock_send):
            resp = client.post("/auth/register", json={"email": email, "password": _PW, "name": "X"})
        self.assertEqual(resp.status_code, 201, resp.text)
        _KNOWN_UIDS.append(resp.json()["account"]["id"])
        self.assertEqual(mock_send.await_count, 1)
        self.assertFalse(resp.json()["account"]["email_verified"])


class TestRateLimitAuthScope(unittest.TestCase):
    def test_scope_mapping(self):
        self.assertEqual(_scope_for_path("/auth/login"), "auth")
        self.assertEqual(_scope_for_path("/auth/register"), "auth")
        self.assertEqual(_scope_for_path("/auth/password/reset"), "auth")
        self.assertEqual(_scope_for_path("/users/register"), "register")

    def test_auth_scope_limits(self):
        identity = f"unit-{uuid.uuid4().hex}"
        ok1, _ = check_rate_limit("auth", identity, kind="ip", burst=1, sustained=1)
        self.assertTrue(ok1)
        ok2, _ = check_rate_limit("auth", identity, kind="ip", burst=1, sustained=1)
        self.assertFalse(ok2)


class TestRegisterUsernameRoute(unittest.TestCase):
    """W9a/b via route: auto username di respons, login by identifier (3 cara), validasi 400."""

    def test_register_returns_auto_username(self):
        client = _client()
        email = _email()
        resp = client.post("/auth/register", json={"email": email, "password": _PW, "name": "U"})
        self.assertEqual(resp.status_code, 201, resp.text)
        account = resp.json()["account"]
        _KNOWN_UIDS.append(account["id"])
        self.assertEqual(account["username"], email.split("@")[0])

    def test_login_username_three_ways(self):
        email = _email()
        uname = f"uni{uuid.uuid4().hex[:8]}"
        seed = _client()
        _register_verified(seed, email, username=uname)
        # client baru per percobaan: tanpa cookie sesi → lolos CSRF double-submit
        for payload in (
            {"identifier": uname, "password": _PW},
            {"identifier": uname.upper(), "password": _PW},
            {"email": uname, "password": _PW},
            {"identifier": email, "password": _PW},
            {"email": email, "password": _PW},
        ):
            r = _client().post("/auth/login", json=payload)
            self.assertEqual(r.status_code, 200, f"{payload}: {r.text}")

    def test_register_invalid_username_400(self):
        client = _client()
        resp = client.post("/auth/register", json={"email": _email(), "password": _PW, "name": "U", "username": "x"})
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_register_duplicate_username_400(self):
        client = _client()
        uname = f"dup{uuid.uuid4().hex[:8]}"
        first = client.post("/auth/register", json={"email": _email(), "password": _PW, "name": "A", "username": uname})
        self.assertEqual(first.status_code, 201, first.text)
        _KNOWN_UIDS.append(first.json()["account"]["id"])
        second = client.post(
            "/auth/register", json={"email": _email(), "password": _PW, "name": "B", "username": uname.upper()}
        )
        self.assertEqual(second.status_code, 400, second.text)

    def test_login_without_identifier_400(self):
        client = _client()
        resp = client.post("/auth/login", json={"password": _PW})
        self.assertEqual(resp.status_code, 400)


class TestRegisterDuplicate409(unittest.TestCase):
    """W9c: duplikat email → 409 + hint_provider sesuai provider akun lama (fail-closed)."""

    def _attempt(self, provider: str):
        client = _client()
        email = _email()
        first = client.post("/auth/register", json={"email": email, "password": _PW, "name": "A"})
        self.assertEqual(first.status_code, 201, first.text)
        uid = first.json()["account"]["id"]
        _KNOWN_UIDS.append(uid)
        if provider != "password":
            with get_session() as db:
                row = db.query(User).filter(User.id == uid).one()
                row.auth_provider = provider
                row.oauth_provider_id = f"{provider}-dup-1"
                db.commit()
        return client.post("/auth/register", json={"email": email.upper(), "password": _PW, "name": "B"})

    def test_hint_google(self):
        dup = self._attempt("google")
        self.assertEqual(dup.status_code, 409, dup.text)
        detail = dup.json()["detail"]
        self.assertEqual(detail["hint_provider"], "google")
        self.assertIn("sudah terdaftar", detail["message"])

    def test_hint_github(self):
        dup = self._attempt("github")
        self.assertEqual(dup.status_code, 409, dup.text)
        self.assertEqual(dup.json()["detail"]["hint_provider"], "github")

    def test_no_hint_when_password(self):
        dup = self._attempt("password")
        self.assertEqual(dup.status_code, 409, dup.text)
        self.assertIsNone(dup.json()["detail"]["hint_provider"])


class TestConnectedProvidersMe(unittest.TestCase):
    """W9b: /auth/me mengekspos connected_providers + username."""

    def test_me_connected_providers(self):
        client = _client()
        email = _email()
        account = _register_verified(client, email)
        r = client.post("/auth/login", json={"email": email, "password": _PW})
        self.assertEqual(r.status_code, 200, r.text)
        me = client.get("/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["connected_providers"], [])
        self.assertEqual(me.json()["username"], account["username"])
        with get_session() as db:
            row = db.query(User).filter(User.email == email).one()
            row.auth_provider = "google"
            row.oauth_provider_id = "g-me-1"
            db.commit()
        me2 = client.get("/auth/me")
        self.assertEqual(me2.json()["connected_providers"], ["google"])


class TestOAuthUnverifiedGateRoute(unittest.TestCase):
    """W9d e2e: callback email_verified=false → reason=email_unverified, tanpa user/sesi."""

    def test_callback_unverified_rejected(self):
        client = _client()
        email = _email()
        with (
            patch.dict(os.environ, _OAUTH_ENABLED_ENV),
            patch("src.core.auth.oauth.httpx.AsyncClient", _FakeAsyncClient),
        ):
            _FakeAsyncClient.userinfo = {
                "sub": f"g-{uuid.uuid4().hex[:8]}",
                "email": email,
                "email_verified": False,
                "name": "Belum Verif",
            }
            state = _oauth_state(client)
            cb = client.get(
                f"/auth/oauth/google/callback?code=unit-code&state={state}",
                follow_redirects=False,
            )
        self.assertEqual(cb.status_code, 302, cb.text)
        self.assertIn("reason=email_unverified", cb.headers["location"])
        self.assertFalse(any("ayesh_session=" in c for c in cb.headers.get_list("set-cookie")))
        with get_session() as db:
            self.assertIsNone(db.query(User).filter(User.email == email).first())


class TestSessionManagement(unittest.TestCase):
    """W6: daftar & revoke sesi aktif (ownership-scoped, CSRF, fail-closed)."""

    def setUp(self):
        self.client = _client()
        self.email = _email()
        _register_verified(self.client, self.email)
        login = self.client.post("/auth/login", json={"email": self.email, "password": _PW})
        self.assertEqual(login.status_code, 200, login.text)
        self.csrf = self.client.cookies.get("ayesh_csrf")

    def test_list_sessions_marks_current(self):
        r = self.client.get("/auth/sessions")
        self.assertEqual(r.status_code, 200, r.text)
        sessions = r.json()["sessions"]
        self.assertEqual(r.json()["count"], len(sessions))
        self.assertGreaterEqual(len(sessions), 1)
        self.assertTrue(any(s["current"] for s in sessions))
        for key in ("id", "ip", "user_agent", "created_at", "last_active_at", "expires_at", "current"):
            self.assertIn(key, sessions[0])

    def test_revoke_other_session_kills_it(self):
        other = _client()
        self.assertEqual(other.post("/auth/login", json={"email": self.email, "password": _PW}).status_code, 200)
        mine = self.client.get("/auth/sessions").json()["sessions"]
        self.assertEqual(len(mine), 2)
        target = next(s for s in mine if not s["current"])
        d = self.client.delete(f"/auth/sessions/{target['id']}", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(d.status_code, 200, d.text)
        self.assertFalse(d.json()["current"])
        self.assertEqual(other.get("/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/auth/sessions").json()["count"], 1)

    def test_revoke_foreign_session_404(self):
        other = _client()
        email_b = _email()
        _register_verified(other, email_b)
        self.assertEqual(other.post("/auth/login", json={"email": email_b, "password": _PW}).status_code, 200)
        sid_b = other.get("/auth/sessions").json()["sessions"][0]["id"]
        d = self.client.delete(f"/auth/sessions/{sid_b}", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(d.status_code, 404, d.text)
        self.assertEqual(other.get("/auth/me").status_code, 200)

    def test_revoke_unknown_404(self):
        d = self.client.delete(
            "/auth/sessions/00000000-0000-0000-0000-000000000000", headers={"X-CSRF-Token": self.csrf}
        )
        self.assertEqual(d.status_code, 404)

    def test_revoke_requires_csrf(self):
        d = self.client.delete("/auth/sessions/xyz")
        self.assertEqual(d.status_code, 403)
        self.assertEqual(d.json()["error"], "csrf_token")

    def test_revoke_current_clears_cookies(self):
        cur = next(s for s in self.client.get("/auth/sessions").json()["sessions"] if s["current"])
        d = self.client.delete(f"/auth/sessions/{cur['id']}", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(d.status_code, 200, d.text)
        self.assertTrue(d.json()["current"])
        self.assertEqual(self.client.get("/auth/me").status_code, 401)


class TestUpdateMe(unittest.TestCase):
    """W6: PATCH /auth/me — display name saja (email change alur terpisah)."""

    def setUp(self):
        self.client = _client()
        self.email = _email()
        _register_verified(self.client, self.email)
        login = self.client.post("/auth/login", json={"email": self.email, "password": _PW})
        self.assertEqual(login.status_code, 200, login.text)
        self.csrf = self.client.cookies.get("ayesh_csrf")

    def test_patch_name_ok_persists(self):
        r = self.client.patch("/auth/me", json={"name": "Nama Baru"}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["name"], "Nama Baru")
        me = self.client.get("/auth/me")
        self.assertEqual(me.json()["name"], "Nama Baru")
        self.assertEqual(me.json()["email"], self.email)

    def test_patch_requires_csrf(self):
        r = self.client.patch("/auth/me", json={"name": "X"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"], "csrf_token")

    def test_patch_requires_auth(self):
        r = _client().patch("/auth/me", json={"name": "X"})
        self.assertEqual(r.status_code, 401)

    def test_patch_blank_name_422(self):
        r = self.client.patch("/auth/me", json={"name": "   "}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 422)


class TestDeleteAccountSelf(unittest.TestCase):
    """W6: DELETE /auth/me — hard-gate password + 2FA, soft-delete anonim, fail-closed."""

    def setUp(self):
        self.client = _client()
        self.email = _email()
        self.account = _register_verified(self.client, self.email)
        login = self.client.post("/auth/login", json={"email": self.email, "password": _PW})
        self.assertEqual(login.status_code, 200, login.text)
        self.csrf = self.client.cookies.get("ayesh_csrf")

    def _delete(self, payload: dict, client=None):
        return (client or self.client).request("DELETE", "/auth/me", json=payload, headers={"X-CSRF-Token": self.csrf})

    def test_requires_csrf(self):
        r = self.client.request("DELETE", "/auth/me", json={"password": _PW})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"], "csrf_token")

    def test_wrong_password_keeps_account(self):
        r = self._delete({"password": "wrong-pass-99"})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("salah", r.json()["detail"])
        self.assertEqual(self.client.get("/auth/me").status_code, 200)

    def test_delete_ok_soft_delete_and_anonymize(self):
        r = self._delete({"password": _PW})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "deleted")
        # cookie dibersihkan → sesi mati
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        # login ulang dengan email lama gagal
        fresh = _client()
        again = fresh.post("/auth/login", json={"email": self.email, "password": _PW})
        self.assertEqual(again.status_code, 401, again.text)
        # DB: nonaktif, email dianonimkan, kredensial dicabut
        with get_session() as db:
            row = db.query(User).filter(User.id == self.account["id"]).one()
            self.assertFalse(row.active)
            self.assertNotEqual(row.email, self.email)
            self.assertIsNone(row.password_hash)
            self.assertIsNone(row.username)
            self.assertIsNone(row.totp_secret)

    def test_oauth_only_without_password_400(self):
        with get_session() as db:
            row = db.query(User).filter(User.id == self.account["id"]).one()
            row.password_hash = None
            db.commit()
        r = self._delete({"password": _PW})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("OAuth-only", r.json()["detail"])
        self.assertEqual(self.client.get("/auth/me").status_code, 200)

    def test_delete_with_2fa_requires_valid_code(self):
        setup = self.client.post("/auth/2fa/setup", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(setup.status_code, 200, setup.text)
        secret = setup.json()["secret"]
        confirm = self.client.post(
            "/auth/2fa/confirm", json={"code": pyotp.TOTP(secret).now()}, headers={"X-CSRF-Token": self.csrf}
        )
        self.assertEqual(confirm.status_code, 200, confirm.text)
        # tanpa kode → ditolak
        r1 = self._delete({"password": _PW})
        self.assertEqual(r1.status_code, 400, r1.text)
        self.assertIn("2FA aktif", r1.json()["detail"])
        # kode salah → ditolak
        r2 = self._delete({"password": _PW, "code": "000000"})
        self.assertEqual(r2.status_code, 400, r2.text)
        # kode benar → terhapus
        r3 = self._delete({"password": _PW, "code": pyotp.TOTP(secret).now()})
        self.assertEqual(r3.status_code, 200, r3.text)


class TestBackupRegenerate(unittest.TestCase):
    """W6: POST /auth/2fa/backup/regenerate — 10 kode baru, kode lama tak berlaku."""

    def setUp(self):
        self.client = _client()
        self.email = _email()
        _register_verified(self.client, self.email)
        login = self.client.post("/auth/login", json={"email": self.email, "password": _PW})
        self.assertEqual(login.status_code, 200, login.text)
        self.csrf = self.client.cookies.get("ayesh_csrf")

    def test_requires_2fa(self):
        r = self.client.post("/auth/2fa/backup/regenerate", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("2FA", r.json()["detail"])

    def test_requires_csrf(self):
        r = self.client.post("/auth/2fa/backup/regenerate")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"], "csrf_token")

    def test_regenerate_invalidates_old_codes(self):
        setup = self.client.post("/auth/2fa/setup", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(setup.status_code, 200, setup.text)
        secret = setup.json()["secret"]
        confirm = self.client.post(
            "/auth/2fa/confirm", json={"code": pyotp.TOTP(secret).now()}, headers={"X-CSRF-Token": self.csrf}
        )
        old = confirm.json()["backup_codes"]
        self.assertEqual(len(old), 10)

        r = self.client.post("/auth/2fa/backup/regenerate", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200, r.text)
        new = r.json()["backup_codes"]
        self.assertEqual(len(new), 10)
        self.assertRegex(new[0], r"^[0-9A-F]{4}-[0-9A-F]{4}$")
        self.assertFalse(set(new) & set(old))

        # kode lama ditolak (challenge sekali pakai → login ulang untuk kode baru)
        fresh = _client()
        login1 = fresh.post("/auth/login", json={"email": self.email, "password": _PW})
        self.assertEqual(login1.json()["status"], "2fa_required")
        bad = fresh.post("/auth/login/2fa", json={"challenge": login1.json()["challenge"], "code": old[0]})
        self.assertEqual(bad.status_code, 401, bad.text)
        login2 = fresh.post("/auth/login", json={"email": self.email, "password": _PW})
        ok = fresh.post("/auth/login/2fa", json={"challenge": login2.json()["challenge"], "code": new[0]})
        self.assertEqual(ok.status_code, 200, ok.text)


class TestLinkedAccountsRoutes(unittest.TestCase):
    """W9e: GET/DELETE /auth/linked-accounts — daftar, unlink, guard koneksi terakhir."""

    def setUp(self):
        self.client = _client()
        self.email = _email()
        self.account = _register_verified(self.client, self.email)
        login = self.client.post("/auth/login", json={"email": self.email, "password": _PW})
        self.assertEqual(login.status_code, 200, login.text)
        self.csrf = self.client.cookies.get("ayesh_csrf")

    def _link_row(self, provider: str) -> str:
        pid = f"{provider}-{uuid.uuid4().hex[:8]}"
        with get_session() as db:
            db.add(
                AuthOAuthAccount(
                    user_id=self.account["id"],
                    provider=provider,
                    provider_id=pid,
                    email=self.email,
                    email_verified=True,
                )
            )
            db.commit()
        return pid

    def test_list_empty_then_after_link(self):
        r = self.client.get("/auth/linked-accounts")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["accounts"], [])
        self.assertEqual(r.json()["count"], 0)
        self._link_row("google")
        r2 = self.client.get("/auth/linked-accounts")
        self.assertEqual(r2.status_code, 200)
        accounts = r2.json()["accounts"]
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["provider"], "google")
        self.assertTrue(accounts[0]["email_verified"])
        self.assertEqual(accounts[0]["email"], self.email)

    def test_unlink_with_password_ok(self):
        self._link_row("google")
        r = self.client.delete("/auth/linked-accounts/google", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "unlinked")
        self.assertEqual(self.client.get("/auth/linked-accounts").json()["count"], 0)

    def test_unlink_requires_csrf(self):
        self._link_row("google")
        r = self.client.delete("/auth/linked-accounts/google")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"], "csrf_token")

    def test_unlink_unknown_404(self):
        r = self.client.delete("/auth/linked-accounts/github", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 404, r.text)

    def test_unlink_requires_auth(self):
        r = _client().delete("/auth/linked-accounts/google", headers={"X-CSRF-Token": "x"})
        self.assertEqual(r.status_code, 401)

    def test_unlink_last_provider_oauth_only_guard(self):
        """OAuth-only: koneksi terakhir tak boleh dilepas; multi-provider (W9e) boleh dilepas satu-satu."""
        oauth_client = _client()
        oauth_email = _email()
        with (
            patch.dict(os.environ, _OAUTH_ENABLED_ENV),
            patch("src.core.auth.oauth.httpx.AsyncClient", _FakeAsyncClient),
        ):
            _FakeAsyncClient.userinfo = {
                "sub": f"g-{uuid.uuid4().hex[:8]}",
                "email": oauth_email,
                "email_verified": True,
                "name": "OAuthOnly",
            }
            state = _oauth_state(oauth_client)
            cb = oauth_client.get(f"/auth/oauth/google/callback?code=unit-code&state={state}", follow_redirects=False)
        self.assertEqual(cb.status_code, 302, cb.text)
        self.assertIn("auth=ok", cb.headers["location"])
        uid = oauth_client.get("/auth/me").json()["id"]
        _KNOWN_UIDS.append(uid)
        csrf = oauth_client.cookies.get("ayesh_csrf")

        # satu-satunya koneksi, tanpa password → ditolak (anti orphan)
        un1 = oauth_client.delete("/auth/linked-accounts/google", headers={"X-CSRF-Token": csrf})
        self.assertEqual(un1.status_code, 400, un1.text)
        self.assertIn("terakhir", un1.json()["detail"])

        # provider kedua terpasang (multi-provider) → koneksi pertama boleh dilepas
        with get_session() as db:
            db.add(
                AuthOAuthAccount(
                    user_id=uid,
                    provider="github",
                    provider_id=f"gh-{uuid.uuid4().hex[:8]}",
                    email=oauth_email,
                    email_verified=True,
                )
            )
            db.commit()
        un2 = oauth_client.delete("/auth/linked-accounts/google", headers={"X-CSRF-Token": csrf})
        self.assertEqual(un2.status_code, 200, un2.text)
        remaining = oauth_client.get("/auth/linked-accounts").json()["accounts"]
        self.assertEqual([a["provider"] for a in remaining], ["github"])

        # github kini satu-satunya tanpa password → ditolak lagi
        un3 = oauth_client.delete("/auth/linked-accounts/github", headers={"X-CSRF-Token": csrf})
        self.assertEqual(un3.status_code, 400, un3.text)


if __name__ == "__main__":
    unittest.main()
