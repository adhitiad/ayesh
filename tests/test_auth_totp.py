"""Unit test TOTP 2FA + backup codes sekali-pakai. Pure Python (pyotp)."""

import unittest

import pyotp

from src.core.auth.totp import (
    generate_backup_codes,
    generate_totp_secret,
    hash_backup_codes,
    totp_uri,
    verify_backup_code,
    verify_totp,
)


class TestTotp(unittest.TestCase):
    def test_generate_secret(self):
        secret = generate_totp_secret()
        self.assertTrue(secret)
        self.assertTrue(len(secret) >= 16)

    def test_uri(self):
        uri = totp_uri(generate_totp_secret(), "user@example.com")
        self.assertIn("otpauth://totp/", uri)
        self.assertIn("issuer=Ayesh", uri)
        self.assertIn("user%40example.com", uri)

    def test_verify_now(self):
        secret = generate_totp_secret()
        code = pyotp.TOTP(secret).now()
        self.assertTrue(verify_totp(secret, code))
        self.assertFalse(verify_totp(secret, "000000"))
        self.assertFalse(verify_totp(secret, ""))

    def test_verify_window_neighbor(self):
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        self.assertTrue(verify_totp(secret, code))
        # valid_window=1 → langkah berikutnya (30s ke depan) tetap diterima
        import time

        code_next = totp.at(int(time.time()) + 30)
        self.assertTrue(verify_totp(secret, code_next))

    def test_verify_fail_closed(self):
        self.assertFalse(verify_totp("", "123456"))
        self.assertFalse(verify_totp(None, "123456"))


class TestBackupCodes(unittest.TestCase):
    def test_format(self):
        codes = generate_backup_codes(10)
        self.assertEqual(len(codes), 10)
        for c in codes:
            self.assertRegex(c, r"^[0-9A-F]{4}-[0-9A-F]{4}$")

    def test_hash_and_verify_one_time(self):
        codes = generate_backup_codes(10)
        stored = hash_backup_codes(codes)
        ok, new_stored = verify_backup_code(stored, codes[0])
        self.assertTrue(ok)
        self.assertIsNotNone(new_stored)
        # second use must fail (one-time)
        ok2, _ = verify_backup_code(new_stored, codes[0])
        self.assertFalse(ok2)
        # other code still usable
        ok3, _ = verify_backup_code(new_stored, codes[1])
        self.assertTrue(ok3)

    def test_wrong_code(self):
        stored = hash_backup_codes(generate_backup_codes(5))
        ok, new_stored = verify_backup_code(stored, "DEAD-BEEF")
        self.assertFalse(ok)
        self.assertIsNone(new_stored)

    def test_fail_closed_malformed(self):
        self.assertFalse(verify_backup_code(None, "AAAA-BBBB")[0])
        self.assertFalse(verify_backup_code("", "AAAA-BBBB")[0])
        self.assertFalse(verify_backup_code("not-json", "AAAA-BBBB")[0])
        self.assertFalse(verify_backup_code('{"a":1}', "AAAA-BBBB")[0])
        self.assertFalse(verify_backup_code("[]", "AAAA-BBBB")[0])

    def test_normalize(self):
        codes = generate_backup_codes(10)
        stored = hash_backup_codes(codes)
        lower = codes[0].lower()
        ok, _ = verify_backup_code(stored, lower)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
