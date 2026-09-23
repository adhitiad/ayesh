"""Fast IT test: rotasi API key (key lama valid selama masa tenggang)."""

import os
import unittest
from unittest import mock

from src.core.auth.auth import create_user, rotate_user_key, verify_key


class TestRotationApiKey(unittest.TestCase):
    """Regression untuk fitur rotasi API key (roadmap: key lama tetap valid 24 jam)."""

    def setUp(self):
        self.user = create_user("rot_test_base", "user")

    def test_rotate_generates_new_active_key(self):
        old_key = self.user["api_key"]
        result = rotate_user_key(self.user["id"], grace_hours=24)
        self.assertIsNotNone(result)
        self.assertNotEqual(result["api_key"], old_key)
        self.assertEqual(result["id"], self.user["id"])
        # Key baru langsung aktif, identitas sama
        got = verify_key(result["api_key"])
        self.assertIsNotNone(got)
        self.assertEqual(got["id"], self.user["id"])
        self.assertEqual(got["role"], "user")
        # Key lama masih valid selama masa tenggang
        got_old = verify_key(old_key)
        self.assertIsNotNone(got_old)
        self.assertEqual(got_old["id"], self.user["id"])
        self.assertTrue(result["old_key_valid_until"])

    def test_old_key_invalid_after_grace_expired(self):
        old_key = self.user["api_key"]
        result = rotate_user_key(self.user["id"], grace_hours=0)
        self.assertIsNotNone(result)
        # Masa tenggang sudah lewat -> key lama ditolak
        self.assertIsNone(verify_key(old_key))
        # Key baru tetap valid
        self.assertIsNotNone(verify_key(result["api_key"]))

    def test_rotate_twice_only_keeps_latest_and_current(self):
        key1 = self.user["api_key"]
        r1 = rotate_user_key(self.user["id"], grace_hours=24)
        r2 = rotate_user_key(self.user["id"], grace_hours=24)
        # Key paling lama ditolak
        self.assertIsNone(verify_key(key1))
        # Key hasil rotasi pertama masih berlaku (belum kedaluwarsa)
        self.assertIsNotNone(verify_key(r1["api_key"]))
        # Key terbaru aktif
        self.assertIsNotNone(verify_key(r2["api_key"]))

    def test_rotate_unknown_user_returns_none(self):
        self.assertIsNone(rotate_user_key("tidak-ada-user-xyz"))

    def test_rotate_deactivated_user_returns_none(self):
        r = rotate_user_key(self.user["id"], grace_hours=24)
        self.assertIsNotNone(r)
        # user non-aktif tidak boleh rotasi
        from src.core.auth.auth import deactivate_user

        self.assertTrue(deactivate_user(self.user["id"]))
        self.assertIsNone(rotate_user_key(self.user["id"], grace_hours=24))

    def test_env_grace_override(self):
        old_key = self.user["api_key"]
        with mock.patch.dict(os.environ, {"API_KEY_ROTATION_GRACE_HOURS": "0"}):
            result = rotate_user_key(self.user["id"])
        self.assertIsNotNone(result)
        # grace dari env (0) -> old key langsung invalid
        self.assertIsNone(verify_key(old_key))
        self.assertIsNotNone(verify_key(result["api_key"]))

    def test_rotation_does_not_break_other_users(self):
        other = create_user("rot_test_other", "user")
        self.assertIsNotNone(verify_key(other["api_key"]))
        rotate_user_key(self.user["id"], grace_hours=24)
        self.assertIsNotNone(verify_key(other["api_key"]))
        self.assertIsNotNone(verify_key(self.user["api_key"]))


if __name__ == "__main__":
    unittest.main()
