"""Test akun auth (register/login/reset/2FA/OAuth link) terhadap DB asli.

Membersihkan user + baris auth di tearDown. Email unik per test agar aman
terhadap sisa data antar run.
"""

import os
import unittest
import uuid
from unittest.mock import patch

import pyotp

from src.core.auth.account import (
    authenticate_password,
    change_user_password,
    confirm_email_verification,
    confirm_password_reset,
    confirm_totp,
    delete_account_self,
    disable_totp,
    enable_totp,
    get_account,
    get_user_by_email,
    issue_2fa_challenge,
    issue_password_reset,
    link_oauth_identity,
    list_linked_accounts,
    regenerate_backup_codes,
    register_with_password,
    resend_verification,
    resolve_2fa_challenge,
    unlink_oauth_provider,
    update_display_name,
    verify_user_totp,
)
from src.core.auth.auth_db import backfill_oauth_accounts
from src.core.auth.passwords import verify_password
from src.core.db.db_engine import get_session
from src.core.db.models import AuthOAuthAccount, AuthSession, AuthToken, User

_ENV = patch.dict(
    os.environ,
    {
        "AUTH_DEV_VERIFY": "1",
        "AUTH_REQUIRE_EMAIL_VERIFICATION": "1",
        "AUTH_MIN_PASSWORD_LEN": "8",
    },
)
_KNOWN_UIDS: list[str] = []
_PW = "secret-pass-123"


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


def _email() -> str:
    return f"u{uuid.uuid4().hex[:12]}@test.local"


def _register(email=None, password=None, name="Test User", username=None):
    result = register_with_password(email or _email(), password or _PW, name, username=username)
    _KNOWN_UIDS.append(result["account"]["id"])
    return result


class TestRegisterAndVerify(unittest.TestCase):
    def test_register_normalizes_email(self):
        result = _register(email="  MiXeD@TeSt.LOCAL ")
        account = result["account"]
        _KNOWN_UIDS.append(account["id"])
        self.assertEqual(account["email"], "mixed@test.local")
        self.assertEqual(account["auth_provider"], "password")
        self.assertFalse(account["email_verified"])
        self.assertTrue(account["has_password"])
        self.assertTrue(result["email_verify_token"].startswith("ayt_"))
        self.assertIn("dev_link", result)
        self.assertTrue(result["dev_link"].startswith("http://"))

    def test_register_invalid_email(self):
        with self.assertRaises(ValueError):
            _register(email="nope")

    def test_register_duplicate_email(self):
        email = _email()
        _register(email=email)
        with self.assertRaises(ValueError):
            _register(email=email.upper())

    def test_register_weak_password(self):
        with self.assertRaises(ValueError):
            _register(password="short")

    def test_confirm_verification_one_time(self):
        email = _email()
        result = _register(email=email)
        token = result["email_verify_token"]
        self.assertFalse(get_user_by_email(email).email_verified)  # type: ignore[union-attr]
        self.assertTrue(confirm_email_verification(token))
        self.assertTrue(get_user_by_email(email).email_verified)  # type: ignore[union-attr]
        self.assertFalse(confirm_email_verification(token))


class TestAuthenticate(unittest.TestCase):
    def test_login_flow(self):
        email = _email()
        result = _register(email=email, password=_PW)
        confirm_email_verification(result["email_verify_token"])
        uid, err = authenticate_password(email, _PW)
        self.assertIsNone(err)
        self.assertIsNotNone(uid)

    def test_wrong_password(self):
        email = _email()
        _register(email=email, password=_PW)
        uid, err = authenticate_password(email, "wrong-pass-999")
        self.assertIsNone(uid)
        self.assertEqual(err, "invalid_credentials")
        uid2, err2 = authenticate_password("ghost@test.local", _PW)
        self.assertIsNone(uid2)
        self.assertEqual(err2, "invalid_credentials")

    def test_unverified_cannot_login(self):
        email = _email()
        _register(email=email, password=_PW)
        uid, err = authenticate_password(email, _PW)
        self.assertIsNone(uid)
        self.assertEqual(err, "email_not_verified")

    def test_verification_bypass_env(self):
        with patch.dict(os.environ, {"AUTH_REQUIRE_EMAIL_VERIFICATION": "0"}):
            email = _email()
            _register(email=email, password=_PW)
            uid, err = authenticate_password(email, _PW)
            self.assertIsNone(err)
            self.assertIsNotNone(uid)

    def test_resend_verification(self):
        email = _email()
        _register(email=email)
        result = resend_verification(email)
        self.assertTrue(result["sent"])
        self.assertIn("dev_link", result)
        noop = resend_verification("nobody@test.local")
        self.assertFalse(noop["sent"])


class TestTwoFactor(unittest.TestCase):
    def setUp(self):
        self.email = _email()
        self.result = _register(email=self.email)
        self.uid = self.result["account"]["id"]
        confirm_email_verification(self.result["email_verify_token"])

    def test_full_totp_flow(self):
        secret = pyotp.random_base32()
        self.assertTrue(enable_totp(self.uid, secret))
        account = get_account(self.uid)
        self.assertFalse(account["totp_enabled"])  # pending
        codes = confirm_totp(self.uid, pyotp.TOTP(secret).now())
        self.assertIsNotNone(codes)
        self.assertEqual(len(codes), 10)
        account = get_account(self.uid)
        self.assertTrue(account["totp_enabled"])

    def test_login_with_totp(self):
        secret = pyotp.random_base32()
        enable_totp(self.uid, secret)
        confirm_totp(self.uid, pyotp.TOTP(secret).now())
        challenge = issue_2fa_challenge(self.uid)
        self.assertTrue(challenge.startswith("ayt_"))
        ok, _ = verify_user_totp(self.uid, pyotp.TOTP(secret).now())
        self.assertTrue(ok)
        ok2, _ = verify_user_totp(self.uid, "000000")
        self.assertFalse(ok2)
        # challenge once
        uid = resolve_2fa_challenge(challenge)
        self.assertEqual(uid, self.uid)
        self.assertIsNone(resolve_2fa_challenge(challenge))

    def test_backup_code_consumed(self):
        secret = pyotp.random_base32()
        enable_totp(self.uid, secret)
        codes = confirm_totp(self.uid, pyotp.TOTP(secret).now())
        ok, _ = verify_user_totp(self.uid, codes[0])
        self.assertTrue(ok)
        ok2, _ = verify_user_totp(self.uid, codes[0])
        self.assertFalse(ok2)

    def test_disable_totp(self):
        secret = pyotp.random_base32()
        enable_totp(self.uid, secret)
        confirm_totp(self.uid, pyotp.TOTP(secret).now())
        self.assertFalse(disable_totp(self.uid, "wrong-pass"))
        self.assertTrue(disable_totp(self.uid, "secret-pass-123"))
        account = get_account(self.uid)
        self.assertFalse(account["totp_enabled"])


class TestPasswordReset(unittest.TestCase):
    def setUp(self):
        self.email = _email()
        self.result = _register(email=self.email)
        self.uid = self.result["account"]["id"]
        confirm_email_verification(self.result["email_verify_token"])

    def test_reset_flow(self):
        issue = issue_password_reset(self.email)
        self.assertTrue(issue["sent"])
        token = issue["reset_token"]
        self.assertTrue(confirm_password_reset(token, "new-pass-456"))
        with get_session() as db:
            user = db.query(User).filter(User.id == self.uid).one()
            self.assertFalse(verify_password("secret-pass-123", user.password_hash))
            self.assertTrue(verify_password("new-pass-456", user.password_hash))
        # token one-time
        self.assertFalse(confirm_password_reset(token, "another-pass-1"))

    def test_reset_unknown_email_noop(self):
        issue = issue_password_reset("ghost@test.local")
        self.assertFalse(issue["sent"])

    def test_change_password(self):
        changed = change_user_password(self.uid, "secret-pass-123", "new-pass-789")
        self.assertTrue(changed["changed"])
        with get_session() as db:
            user = db.query(User).filter(User.id == self.uid).one()
            self.assertTrue(verify_password("new-pass-789", user.password_hash))
        with self.assertRaises(ValueError):
            change_user_password(self.uid, "wrong-pass", "new-pass-000")


class TestOAuthLink(unittest.TestCase):
    def test_create_from_profile(self):
        profile = {
            "provider": "google",
            "provider_user_id": "g1",
            "email": f"g{uuid.uuid4().hex[:8]}@test.local",
            "name": "OAuth",
            "email_verified": True,
        }
        user = link_oauth_identity(profile)
        self.assertIsNotNone(user["id"])
        _KNOWN_UIDS.append(user["id"])
        account = get_account(user["id"])
        self.assertEqual(account["email"], profile["email"])
        # W9a: akun OAuth baru otomatis dapat username = local-part email
        self.assertEqual(account["username"], profile["email"].split("@")[0])
        self.assertEqual(account["connected_providers"], ["google"])

    def test_same_provider_id_persists(self):
        email = _email()
        profile = {
            "provider": "github",
            "provider_user_id": "gh_1",
            "email": email,
            "name": "Gh",
            "email_verified": True,
        }
        user1 = link_oauth_identity(profile)
        _KNOWN_UIDS.append(user1["id"])
        user2 = link_oauth_identity(dict(profile, email=f"other-{email}"))
        self.assertEqual(user1["id"], user2["id"])

    def test_multi_provider_link_allowed(self):
        """W9e: email sama boleh punya banyak provider (menimpa aturan lama W9d)."""
        email = _email()
        first = link_oauth_identity(
            {"provider": "google", "provider_user_id": f"g2-{uuid.uuid4().hex[:8]}", "email": email, "name": "X", "email_verified": True}
        )
        _KNOWN_UIDS.append(first["id"])
        second = link_oauth_identity(
            {"provider": "github", "provider_user_id": f"gh2-{uuid.uuid4().hex[:8]}", "email": email, "name": "G", "email_verified": True}
        )
        self.assertEqual(second["id"], first["id"])
        account = get_account(first["id"])
        self.assertEqual(account["connected_providers"], ["github", "google"])

    def test_email_in_use_same_provider_new_id(self):
        """Identitas terikat ke provider yang sama tapi provider_id lain → tetap email_in_use."""
        email = _email()
        first = link_oauth_identity(
            {"provider": "google", "provider_user_id": f"g2-{uuid.uuid4().hex[:8]}", "email": email, "name": "X", "email_verified": True}
        )
        _KNOWN_UIDS.append(first["id"])
        with self.assertRaises(ValueError) as ctx:
            link_oauth_identity(
                {
                    "provider": "google",
                    "provider_user_id": f"g-other-{uuid.uuid4().hex[:8]}",
                    "email": email,
                    "name": "Y",
                    "email_verified": True,
                }
            )
        self.assertEqual(str(ctx.exception), "email_in_use")

    def test_link_to_existing_password_user(self):
        email = _email()
        result = _register(email=email)
        _KNOWN_UIDS.append(result["account"]["id"])
        user = link_oauth_identity(
            {"provider": "google", "provider_user_id": "g3", "email": email, "name": "Link", "email_verified": True}
        )
        self.assertEqual(user["id"], result["account"]["id"])
        account = get_account(user["id"])
        self.assertTrue(account["email_verified"])
        self.assertEqual(account["connected_providers"], ["google"])


class TestUsernameRegister(unittest.TestCase):
    """W9a/b: username — auto dari local-part, normalisasi, validasi, duplikat, login by username."""

    def test_auto_username_from_local_part(self):
        local = f"auto{uuid.uuid4().hex[:8]}"
        result = _register(email=f"{local}@test.local")
        self.assertEqual(result["account"]["username"], local)

    def test_explicit_username_normalized(self):
        result = _register(username="  Mixed.User ")
        self.assertEqual(result["account"]["username"], "mixed.user")

    def test_username_invalid_rejected(self):
        for bad in ("ab", "bad name", "user@x", "x" * 33):
            with self.assertRaises(ValueError, msg=bad):
                _register(username=bad)

    def test_username_duplicate_rejected(self):
        _register(username="dupcheckuser")
        with self.assertRaises(ValueError):
            _register(username="DUPCHECKUSER")

    def test_auto_username_collision_gets_suffix(self):
        base = f"coll{uuid.uuid4().hex[:8]}"
        first = _register(email=f"{base}@one.test")
        second = _register(email=f"{base}@two.test")
        self.assertEqual(first["account"]["username"], base)
        self.assertEqual(second["account"]["username"], f"{base}-2")

    def test_login_by_username_identifier(self):
        email = _email()
        uname = f"log{uuid.uuid4().hex[:8]}"
        result = _register(email=email, username=uname)
        confirm_email_verification(result["email_verify_token"])
        uid, err = authenticate_password(uname, _PW)
        self.assertIsNone(err)
        uid2, err2 = authenticate_password(uname.upper(), _PW)
        self.assertIsNone(err2)
        self.assertEqual(uid, uid2)
        uid3, err3 = authenticate_password(email, _PW)
        self.assertIsNone(err3)
        self.assertEqual(uid, uid3)


class TestOAuthEmailVerifiedGate(unittest.TestCase):
    """W9d: profil OAuth dengan email_verified=false/tanpa kunci → tolak fail-closed."""

    def test_reject_unverified_auto_link(self):
        email = _email()
        result = _register(email=email)
        with self.assertRaises(ValueError) as ctx:
            link_oauth_identity(
                {
                    "provider": "google",
                    "provider_user_id": f"gu-{uuid.uuid4().hex[:8]}",
                    "email": email,
                    "name": "X",
                    "email_verified": False,
                }
            )
        self.assertEqual(str(ctx.exception), "email_unverified")
        account = get_account(result["account"]["id"])
        self.assertEqual(account["auth_provider"], "password")
        self.assertEqual(account["connected_providers"], [])

    def test_reject_unverified_new_account(self):
        email = _email()
        with self.assertRaises(ValueError) as ctx:
            link_oauth_identity(
                {
                    "provider": "github",
                    "provider_user_id": f"gu-{uuid.uuid4().hex[:8]}",
                    "email": email,
                    "name": "X",
                    "email_verified": False,
                }
            )
        self.assertEqual(str(ctx.exception), "email_unverified")
        self.assertIsNone(get_user_by_email(email))

    def test_missing_email_verified_rejected(self):
        email = _email()
        with self.assertRaises(ValueError) as ctx:
            link_oauth_identity(
                {"provider": "google", "provider_user_id": f"gu-{uuid.uuid4().hex[:8]}", "email": email, "name": "X"}
            )
        self.assertEqual(str(ctx.exception), "email_unverified")
        self.assertIsNone(get_user_by_email(email))


class TestMultiProviderBackfillW9e(unittest.TestCase):
    """W9e: backfill legacy → auth_oauth_accounts (idempoten)."""

    def test_backfill_legacy_identity(self):
        result = _register()
        uid = result["account"]["id"]
        pid = f"g-bf-{uuid.uuid4().hex[:8]}"
        with get_session() as db:
            row = db.query(User).filter(User.id == uid).one()
            row.auth_provider = "google"
            row.oauth_provider_id = pid
            row.email_verified = True
            db.commit()
        self.assertGreaterEqual(backfill_oauth_accounts(), 1)
        with get_session() as db:
            rows = db.query(AuthOAuthAccount).filter(AuthOAuthAccount.user_id == uid).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(str(rows[0].provider), "google")
            self.assertEqual(str(rows[0].provider_id), pid)
            self.assertTrue(bool(rows[0].email_verified))
        # idempoten: panggil ulang tidak menggandakan baris
        self.assertEqual(backfill_oauth_accounts(), 0)


class TestSelfServiceW6(unittest.TestCase):
    """W6: profil, backup code, hapus-akun mandiri (unit)."""

    def setUp(self):
        self.email = _email()
        self.result = _register(email=self.email)
        self.uid = self.result["account"]["id"]
        confirm_email_verification(self.result["email_verify_token"])

    def test_update_display_name(self):
        account = update_display_name(self.uid, "  Nama Baru  ")
        self.assertEqual(account["name"], "Nama Baru")
        self.assertEqual(account["email"], self.email)
        with self.assertRaises(ValueError):
            update_display_name(self.uid, "   ")
        self.assertIsNone(update_display_name("no-such-user-id", "X"))

    def test_regenerate_requires_and_rotates_codes(self):
        self.assertIsNone(regenerate_backup_codes(self.uid))
        secret = pyotp.random_base32()
        enable_totp(self.uid, secret)
        old = confirm_totp(self.uid, pyotp.TOTP(secret).now())
        self.assertIsNotNone(old)
        new = regenerate_backup_codes(self.uid)
        self.assertEqual(len(new), 10)
        self.assertFalse(set(new) & set(old))
        ok, _ = verify_user_totp(self.uid, new[0])
        self.assertTrue(ok)
        stale, _ = verify_user_totp(self.uid, old[0])
        self.assertFalse(stale)

    def test_delete_account_self_gates(self):
        self.assertEqual(delete_account_self(self.uid, "wrong-pass"), "bad_password")
        with get_session() as db:
            db.query(User).filter(User.id == self.uid).one().password_hash = None
            db.commit()
        self.assertEqual(delete_account_self(self.uid, _PW), "no_password")

    def test_delete_account_self_ok(self):
        self.assertIsNone(delete_account_self(self.uid, _PW))
        with get_session() as db:
            row = db.query(User).filter(User.id == self.uid).one()
            self.assertFalse(row.active)
            self.assertNotEqual(row.email, self.email)
            self.assertIsNone(row.password_hash)
        uid, err = authenticate_password(self.email, _PW)
        self.assertIsNone(uid)
        self.assertIsNotNone(err)


class TestLinkedAccountsW9e(unittest.TestCase):
    """W9e: list_linked_accounts + unlink guard (unit)."""

    def setUp(self):
        self.result = _register()
        self.uid = self.result["account"]["id"]

    def _link(self, provider: str) -> None:
        with get_session() as db:
            db.add(
                AuthOAuthAccount(
                    user_id=self.uid,
                    provider=provider,
                    provider_id=f"{provider}-{uuid.uuid4().hex[:8]}",
                    email=self.result["account"]["email"],
                    email_verified=True,
                )
            )
            db.commit()

    def test_list_table_then_legacy(self):
        self.assertEqual(list_linked_accounts(self.uid), [])
        self._link("google")
        with get_session() as db:
            row = db.query(User).filter(User.id == self.uid).one()
            row.auth_provider = "github"
            row.oauth_provider_id = "gh-legacy-1"
            db.commit()
        providers = [a["provider"] for a in list_linked_accounts(self.uid)]
        self.assertEqual(providers, ["google", "github"])

    def test_unlink_guards(self):
        self.assertEqual(unlink_oauth_provider(self.uid, "bogus"), "not_found")
        self.assertEqual(unlink_oauth_provider(self.uid, "google"), "not_found")
        # OAuth-only + satu koneksi → last_provider (anti orphan)
        self._link("google")
        with get_session() as db:
            db.query(User).filter(User.id == self.uid).one().password_hash = None
            db.commit()
        self.assertEqual(unlink_oauth_provider(self.uid, "google"), "last_provider")
        # multi-provider → boleh lepas satu
        self._link("github")
        self.assertIsNone(unlink_oauth_provider(self.uid, "google"))
        self.assertEqual([a["provider"] for a in list_linked_accounts(self.uid)], ["github"])
        # tersisa satu tanpa password → ditolak
        self.assertEqual(unlink_oauth_provider(self.uid, "github"), "last_provider")


if __name__ == "__main__":
    unittest.main()
