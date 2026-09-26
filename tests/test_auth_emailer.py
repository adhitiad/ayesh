"""Unit emailer.send_email dengan SMTP fake (aiosmtplib di-patch): off, OK, gagal."""

import asyncio
import os
import unittest
from unittest.mock import patch

from src.core.auth.emailer import email_enabled, send_email


class _FakeSMTP:
    """Fake aiosmtplib.SMTP: rekam login + pesan; bisa dipaksa gagal."""

    created: list = []
    fail_send = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.auth_user = None
        self.sent: list = []
        _FakeSMTP.created.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def starttls(self):
        return None

    async def login(self, user, password):
        self.auth_user = user

    async def sendmail(self, from_addr, to_addrs, message):
        if _FakeSMTP.fail_send:
            raise RuntimeError("SMTP connection refused")
        self.sent.append((from_addr, to_addrs, message))


def _smtp_env(**overrides) -> dict:
    env = {
        "SMTP_ENABLED": "1",
        "SMTP_HOST": "smtp.test.local",
        "SMTP_USER": "unit@test.local",
        "SMTP_PASSWORD": "pw-unit",
        "SMTP_STARTTLS": "0",
        "SMTP_FROM": "Ayesh <no-reply@test.local>",
    }
    env.update(overrides)
    return env


class TestSendEmail(unittest.TestCase):
    def setUp(self):
        _FakeSMTP.created = []
        _FakeSMTP.fail_send = False

    def test_disabled_env_short_circuits(self):
        env = _smtp_env(SMTP_ENABLED="0")
        with patch.dict(os.environ, env), patch("aiosmtplib.SMTP", _FakeSMTP):
            self.assertFalse(email_enabled())
            ok = asyncio.run(send_email("tujuan@test.local", "Subjek", "<p>isi</p>"))
        self.assertFalse(ok)
        self.assertEqual(_FakeSMTP.created, [])

    def test_success_sends_message(self):
        with patch.dict(os.environ, _smtp_env()), patch("aiosmtplib.SMTP", _FakeSMTP):
            self.assertTrue(email_enabled())
            ok = asyncio.run(send_email("tujuan@test.local", "Subjek", "<p>isi</p>"))
        self.assertTrue(ok)
        self.assertEqual(len(_FakeSMTP.created), 1)
        inst = _FakeSMTP.created[0]
        self.assertEqual(inst.auth_user, "unit@test.local")
        self.assertEqual(inst.kwargs.get("hostname"), "smtp.test.local")
        self.assertEqual(len(inst.sent), 1)
        from_addr, to_addrs, message = inst.sent[0]
        self.assertEqual(from_addr, "Ayesh <no-reply@test.local>")
        self.assertEqual(to_addrs, ["tujuan@test.local"])
        self.assertIn(b"isi", message)

    def test_failure_raises(self):
        _FakeSMTP.fail_send = True
        with (
            patch.dict(os.environ, _smtp_env()),
            patch("aiosmtplib.SMTP", _FakeSMTP),
            self.assertRaises(RuntimeError),
        ):
            asyncio.run(send_email("tujuan@test.local", "Subjek", "<p>isi</p>"))
        self.assertEqual(len(_FakeSMTP.created), 1)


if __name__ == "__main__":
    unittest.main()
