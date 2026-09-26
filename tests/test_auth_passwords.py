"""Unit test hashing password (Argon2id) + kebijakan minimum.

Pure Python — tidak butuh DB/Redis. Fokus: fail-closed (format rusak → False,
bukan exception) dan batas panjang.
"""

import unittest

from src.core.auth.passwords import hash_password, password_policy_ok, verify_password


class TestHashVerify(unittest.TestCase):
    def test_roundtrip(self):
        stored = hash_password("s3cure-pass-123")
        self.assertTrue(stored.startswith("$argon2id$"))
        self.assertTrue(verify_password("s3cure-pass-123", stored))

    def test_wrong_password_false(self):
        stored = hash_password("benar-pass-123")
        self.assertFalse(verify_password("salah-pass-123", stored))

    def test_empty_inputs_false(self):
        stored = hash_password("abc-def-123")
        self.assertFalse(verify_password("", stored))
        self.assertFalse(verify_password("abc-def-123", ""))
        self.assertFalse(verify_password("abc-def-123", None))

    def test_corrupt_hash_false(self):
        self.assertFalse(verify_password("abc-def-123", "not-an-argon2-hash"))
        self.assertFalse(verify_password("abc-def-123", "$argon2id$xx"))
        self.assertFalse(verify_password("abc-def-123", "$argon2id$v=19$m=65536,t=3,p=4$corrupt"))
        self.assertFalse(verify_password(None, None))


class TestPasswordPolicy(unittest.TestCase):
    def test_default_min_8(self):
        ok, err = password_policy_ok("short")
        self.assertFalse(ok)
        self.assertIsNotNone(err)
        self.assertTrue(password_policy_ok("12345678")[0])

    def test_empty(self):
        self.assertFalse(password_policy_ok("")[0])
        self.assertFalse(password_policy_ok(None)[0])

    def test_max_128(self):
        self.assertFalse(password_policy_ok("a" * 129)[0])
        self.assertTrue(password_policy_ok("a" * 128)[0])

    def test_env_override(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"AUTH_MIN_PASSWORD_LEN": "12"}):
            self.assertFalse(password_policy_ok("12345678901")[0])
            self.assertTrue(password_policy_ok("123456789012")[0])


if __name__ == "__main__":
    unittest.main()
