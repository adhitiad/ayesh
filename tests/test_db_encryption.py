"""Unit test enkripsi at-rest kolom DB (Fernet) — tanpa infra.

Jalankan: python -m unittest tests.test_db_encryption
"""

import os
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from src.core.db.encryption import (
    _COVERED,
    EncryptedText,
    _looks_like_token,
    generate_key,
    get_fernet,
    reset_cache,
)


class _EnvKeyMixin:
    """Patch DB_SECRET_KEY + reset cache singleton per test."""

    key: str | None = None

    def setUp(self):
        super().setUp()
        reset_cache()
        env = {"DB_SECRET_KEY": self.key} if self.key is not None else {"DB_SECRET_KEY": ""}
        self._p = patch.dict(os.environ, env, clear=False)
        self._p.start()
        reset_cache()

    def tearDown(self):
        self._p.stop()
        reset_cache()


class TestGenerateKey(unittest.TestCase):
    def test_generate_key_produces_valid_fernet_key(self) -> None:
        k = generate_key()
        self.assertIsInstance(Fernet(k.encode("ascii")), Fernet)

    def test_generate_key_is_urlsafe_ascii(self) -> None:
        k = generate_key()
        self.assertEqual(k, k.strip())
        self.assertEqual(len(k.encode("ascii")), 44)


class TestFeatureOff(_EnvKeyMixin, unittest.TestCase):
    key = None

    def test_get_fernet_returns_none(self) -> None:
        self.assertIsNone(get_fernet())

    def test_bind_passthrough_plaintext(self) -> None:
        col = EncryptedText()
        self.assertEqual(col.process_bind_param("rahasia", None), "rahasia")

    def test_result_passthrough_plaintext(self) -> None:
        col = EncryptedText()
        self.assertEqual(col.process_result_value("rahasia", None), "rahasia")

    def test_bind_none(self) -> None:
        self.assertIsNone(EncryptedText().process_bind_param(None, None))


class TestRoundTrip(_EnvKeyMixin, unittest.TestCase):
    key = "test-key"  # diganti di setUp dengan key valid

    def setUp(self):
        self.key = generate_key()
        super().setUp()

    def test_bind_encrypts_result_decrypts(self) -> None:
        col = EncryptedText()
        secret = "API_KEY=sk-super-rahasia-123"
        token = col.process_bind_param(secret, None)
        self.assertNotEqual(token, secret)
        self.assertTrue(_looks_like_token(token))
        self.assertEqual(col.process_result_value(token, None), secret)

    def test_bind_coerces_non_str(self) -> None:
        col = EncryptedText()
        token = col.process_bind_param(42, None)
        self.assertEqual(col.process_result_value(token, None), "42")

    def test_bind_none_stays_none(self) -> None:
        self.assertIsNone(EncryptedText().process_bind_param(None, None))

    def test_legacy_plaintext_passes_through(self) -> None:
        col = EncryptedText()
        legacy = "ini data plaintext lama sebelum fitur aktif"
        self.assertEqual(col.process_result_value(legacy, None), legacy)

    def test_unicode_roundtrip(self) -> None:
        col = EncryptedText()
        secret = "pesan unicode: äöü, emoji 🚀, tab\t"
        self.assertEqual(col.process_result_value(col.process_bind_param(secret, None), None), secret)


class TestFailClosed(_EnvKeyMixin, unittest.TestCase):
    key = None

    def setUp(self):
        self.key = generate_key()
        super().setUp()

    def test_wrong_key_raises_runtime_error(self) -> None:
        col = EncryptedText()
        token = col.process_bind_param("data penting", None)
        reset_cache()
        with patch.dict(os.environ, {"DB_SECRET_KEY": generate_key()}):
            reset_cache()
            with self.assertRaises(RuntimeError):
                col.process_result_value(token, None)

    def test_tampered_token_raises_runtime_error(self) -> None:
        col = EncryptedText()
        token = col.process_bind_param("data penting", None)
        # ubah 1 char payload di tengah (base64 tetap valid, versi 0x80 utuh) → HMAC gagal
        i = 20
        tampered = token[:i] + ("A" if token[i] != "A" else "B") + token[i + 1 :]
        with self.assertRaises(RuntimeError):
            col.process_result_value(tampered, None)

    def test_invalid_db_secret_key_raises(self) -> None:
        reset_cache()
        with patch.dict(os.environ, {"DB_SECRET_KEY": "bukan-fernet-key"}):
            reset_cache()
            with self.assertRaises(RuntimeError):
                get_fernet()


class TestTokenHeuristic(unittest.TestCase):
    def test_fernet_token_detected(self) -> None:
        f = Fernet(generate_key().encode("ascii"))
        self.assertTrue(_looks_like_token(f.encrypt(b"x").decode()))

    def test_plain_text_not_detected(self) -> None:
        self.assertFalse(_looks_like_token("halo dunia"))
        self.assertFalse(_looks_like_token(""))
        self.assertFalse(_looks_like_token("plain text with spaces"))

    def test_crafted_base64_not_token(self) -> None:
        import base64

        # base64 valid tapi byte pertama bukan 0x80
        self.assertFalse(_looks_like_token(base64.urlsafe_b64encode(b"\x00" * 40).decode()))

    def test_result_none(self) -> None:
        self.assertIsNone(EncryptedText().process_result_value(None, None))


class TestCoveredColumnsMatchModels(unittest.TestCase):
    """Konsistensi: _COVERED = kolom model yang bertipe EncryptedText."""

    def test_covered_columns_are_encrypted_text(self) -> None:
        from src.core.db.models import Base

        models_by_table = {m.__tablename__: m for m in Base.__subclasses__()}
        for table, cols in _COVERED.items():
            self.assertIn(table, models_by_table, f"tabel {table} tidak ada di models")
            model = models_by_table[table]
            for c in cols:
                col = model.__table__.columns[c]
                self.assertIsInstance(col.type, EncryptedText, f"{table}.{c} seharusnya EncryptedText")

    def test_excluded_columns_stay_plain_text(self) -> None:
        from src.core.db.models import AuditLog, UserMemory

        self.assertNotIsInstance(UserMemory.value.property.columns[0].type, EncryptedText)
        self.assertNotIsInstance(AuditLog.details.property.columns[0].type, EncryptedText)


if __name__ == "__main__":
    unittest.main()
