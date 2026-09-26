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
from src.core.db.models import AuthSession, AuthToken, User
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


if __name__ == "__main__":
    unittest.main()
