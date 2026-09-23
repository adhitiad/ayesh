"""Hardening defense-in-depth untuk 4 temuan dismissed (vuln-0001..0004).

Empat temuan diverifikasi tidak tereksploitasi, tapi tetap diperkuat:

- vuln-0001: component-wise symlink audit di ``_safe_path`` (fail-closed).
- vuln-0002: ``effective_auth_config()`` + log konfigurasi auth saat startup.
- vuln-0003: API key hash salted self-describing ``salt$sha256`` + upgrade legacy.
- vuln-0004: blok hostname suffix internal (``.internal``/``.local``/``.svc``)
  dan host metadata non-publik tambahan di ``_validate_url_shape``.

Test tanpa LLM; test DB memakai engine test yang sama seperti test lainnya.
"""

import hashlib
import os
import secrets
import unittest
import uuid
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parents[1]


class TestVuln0001SymlinkComponent(unittest.TestCase):
    """vuln-0001: audit symlink per-komponen, bukan hanya path final."""

    def test_tanpa_symlink_diizinkan(self):
        from src.plugins.file_safety import _check_component_symlinks

        target = os.path.join(str(_ROOT), "output", "file.txt")
        ok, msg = _check_component_symlinks(target, str(_ROOT))
        self.assertTrue(ok, msg)

    def test_symlink_ke_luar_ditolak(self):
        from src.core.auth.approval import current_session
        from src.core.system.workspaces import clear_session_targets, note_target_dir
        from src.plugins.file_safety import _check_component_symlinks

        sid = f"hardening_sym_{uuid.uuid4().hex[:8]}"
        token = current_session.set(sid)
        try:
            with mock.patch.dict(os.environ), tempfile_dirs() as (base, outside):
                ok_note, ap = note_target_dir(sid, base)
                self.assertTrue(ok_note, ap)
                link = os.path.join(base, "link")
                try:
                    os.symlink(outside, link, target_is_directory=True)
                except (OSError, NotImplementedError) as e:
                    self.skipTest(f"symlink tidak didukung di lingkungan ini: {e}")
                ok, msg = _check_component_symlinks(os.path.join(link, "f.txt"), str(_ROOT))
                self.assertFalse(ok)
                self.assertIn("symlink escape", msg)
        finally:
            current_session.reset(token)
            clear_session_targets(sid)

    def test_symlink_ke_dalam_approved_diizinkan(self):
        from src.core.auth.approval import current_session
        from src.core.system.workspaces import clear_session_targets, note_target_dir
        from src.plugins.file_safety import _check_component_symlinks

        sid = f"hardening_sym2_{uuid.uuid4().hex[:8]}"
        token = current_session.set(sid)
        try:
            with tempfile_dirs() as (base, _outside):
                ok_note, ap = note_target_dir(sid, base)
                self.assertTrue(ok_note, ap)
                real = os.path.join(base, "realdir")
                os.makedirs(real, exist_ok=True)
                link = os.path.join(base, "link")
                try:
                    os.symlink(real, link, target_is_directory=True)
                except (OSError, NotImplementedError) as e:
                    self.skipTest(f"symlink tidak didukung di lingkungan ini: {e}")
                ok, msg = _check_component_symlinks(os.path.join(link, "f.txt"), str(_ROOT))
                self.assertTrue(ok, msg)
        finally:
            current_session.reset(token)
            clear_session_targets(sid)

    def test_kegagalan_pemeriksaan_fail_closed(self):
        from src.plugins.file_safety import _check_component_symlinks

        target = os.path.join(str(_ROOT), "output", "file.txt")
        with mock.patch("src.plugins.file_safety.os.path.islink", side_effect=OSError("boom")):
            ok, msg = _check_component_symlinks(target, str(_ROOT))
        self.assertFalse(ok)
        self.assertIn("gagal", msg)

    def test_safe_path_tolak_escape_lewat_symlink(self):
        from src.core.auth.approval import current_session
        from src.core.system.workspaces import clear_session_targets, note_target_dir
        from src.plugins.file_safety import _safe_path

        sid = f"hardening_sym3_{uuid.uuid4().hex[:8]}"
        token = current_session.set(sid)
        try:
            with tempfile_dirs() as (base, outside):
                ok_note, ap = note_target_dir(sid, base)
                self.assertTrue(ok_note, ap)
                link = os.path.join(base, "keluar")
                target_file = os.path.join(outside, "pwned.txt")
                try:
                    os.symlink(target_file, link)
                except (OSError, NotImplementedError) as e:
                    self.skipTest(f"symlink tidak didukung di lingkungan ini: {e}")
                ok, _msg = _safe_path(link)
                self.assertFalse(ok)
        finally:
            current_session.reset(token)
            clear_session_targets(sid)


class TestVuln0002EffectiveAuthConfig(unittest.TestCase):
    """vuln-0002: konfigurasi auth terlihat jelas saat startup (fail-closed)."""

    def test_default_env_auth_aktif(self):
        from src.core.auth.auth_guards import effective_auth_config

        with mock.patch.dict(os.environ):
            os.environ.pop("REQUIRE_API_KEY", None)
            cfg = effective_auth_config()
        self.assertTrue(cfg["require_api_key"])
        self.assertEqual(cfg["require_api_key_raw"], "1")
        self.assertIn("fail-closed", cfg["default"])

    def test_env_nol_tetap_control_plane_tertutup(self):
        from src.core.auth.auth_guards import effective_auth_config

        with mock.patch.dict(os.environ, {"REQUIRE_API_KEY": "0"}):
            cfg = effective_auth_config()
        self.assertFalse(cfg["require_api_key"])
        self.assertIn("require_authenticated", cfg["control_plane"])
        self.assertIn("fail-closed", cfg["control_plane"])

    def test_startup_lifespan_mencatat_auth_config(self):
        src = (_ROOT / "api_server.py").read_text(encoding="utf-8")
        self.assertIn("effective_auth_config()", src)
        self.assertIn("Auth effective config", src)

    def test_env_example_default_aman(self):
        content = (_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("REQUIRE_API_KEY=1", content)


class TestVuln0003SaltedKeyHash(unittest.TestCase):
    """vuln-0003: hash key salted self-describing, legacy tetap dikenali + upgrade."""

    def test_format_self_describing_muat_di_kolom(self):
        from src.core.auth.auth_keys import _hash_key

        key = f"fr_{secrets.token_hex(16)}"
        stored = _hash_key(key)
        self.assertIn("$", stored)
        salt, digest = stored.split("$", 1)
        self.assertEqual(len(salt), 32)
        self.assertEqual(len(digest), 64)
        self.assertLessEqual(len(stored), 128)

    def test_salt_unik_per_hash(self):
        from src.core.auth.auth_keys import _hash_key

        key = f"fr_{secrets.token_hex(16)}"
        self.assertNotEqual(_hash_key(key), _hash_key(key))

    def test_roundtrip_dan_key_salah(self):
        from src.core.auth.auth_keys import _hash_key, _verify_hash

        key = f"fr_{secrets.token_hex(16)}"
        stored = _hash_key(key)
        self.assertTrue(_verify_hash(key, stored))
        self.assertFalse(_verify_hash(key + "x", stored))
        self.assertFalse(_verify_hash(key, ""))

    def test_format_legacy_masih_divalidasi(self):
        from src.core.auth.auth_keys import _hash_key, _verify_hash

        key = f"fr_{secrets.token_hex(16)}"
        legacy = hashlib.sha256(key.encode("utf-8")).hexdigest()
        self.assertTrue(_verify_hash(key, legacy))
        self.assertFalse(_verify_hash(key + "x", legacy))
        self.assertNotEqual(_hash_key(key), legacy)

    def test_verify_key_upgrade_legacy_ke_salt(self):
        from sqlalchemy.orm import sessionmaker

        from src.core.auth.auth_keys import _verify_hash, verify_key
        from src.core.db.db_engine import get_engine
        from src.core.db.models import User

        key = f"fr_{secrets.token_hex(16)}"
        legacy = hashlib.sha256(key.encode("utf-8")).hexdigest()
        uid = str(uuid.uuid4())
        SessionLocal = sessionmaker(bind=get_engine())
        try:
            with SessionLocal() as db:
                db.add(
                    User(
                        id=uid,
                        name="legacy_upgrade_test",
                        key_hash=legacy,
                        prefix=key[:11],
                        role="user",
                        active=True,
                    )
                )
                db.commit()
            got = verify_key(key)
            self.assertIsNotNone(got)
            self.assertEqual(got["id"], uid)
            with SessionLocal() as db:
                row = db.query(User).filter(User.id == uid).first()
                self.assertIsNotNone(row)
                upgraded = str(row.key_hash)
            self.assertIn("$", upgraded)
            self.assertNotEqual(upgraded, legacy)
            self.assertTrue(_verify_hash(key, upgraded))
            self.assertFalse(_verify_hash(key + "x", upgraded))
        finally:
            with SessionLocal() as db:
                db.query(User).filter(User.id == uid).delete()
                db.commit()

    def test_create_user_menghasilkan_hash_salted(self):
        from sqlalchemy.orm import sessionmaker

        from src.core.auth.auth_keys import create_user, verify_key
        from src.core.db.db_engine import get_engine
        from src.core.db.models import User

        user = create_user(f"hardening_salt_{uuid.uuid4().hex[:6]}", "user")
        SessionLocal = sessionmaker(bind=get_engine())
        try:
            self.assertIsNotNone(verify_key(user["api_key"]))
            with SessionLocal() as db:
                row = db.query(User).filter(User.id == user["id"]).first()
                self.assertIsNotNone(row)
                stored = str(row.key_hash)
            self.assertIn("$", stored)
        finally:
            with SessionLocal() as db:
                db.query(User).filter(User.id == user["id"]).delete()
                db.commit()


class TestVuln0004HostnameBlocks(unittest.TestCase):
    """vuln-0004: blok host metadata/internal tambahan di validasi bentuk URL."""

    def _shape(self, url: str) -> bool:
        from src.plugins.web_tools import _validate_url_shape

        return _validate_url_shape(url)

    def test_host_metadata_existing_tetap_diblokir(self):
        for url in (
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://instance-data.ec2.internal/",
            "http://100.100.100.200/",
            "http://[fd00:ec2::254]/",
        ):
            self.assertFalse(self._shape(url), url)

    def test_host_metadata_baru_diblokir(self):
        for url in (
            "http://metadata.tencentyun.com/latest/meta-data/",
            "http://kubernetes.default/api",
        ):
            self.assertFalse(self._shape(url), url)

    def test_suffix_internal_diblokir(self):
        for url in (
            "http://svc-1.internal/",
            "http://printer.local/",
            "http://api.svc/",
            "http://a.b.svc/",
            "http://FOO.INTERNAL./",
            "https://db.local:5432/",
        ):
            self.assertFalse(self._shape(url), url)

    def test_host_publik_tetap_diizinkan(self):
        for url in (
            "http://example.com/",
            "https://sub.example.org/path?q=1",
            "http://localhost/",
        ):
            self.assertTrue(self._shape(url), url)

    def test_skema_non_http_diblokir(self):
        self.assertFalse(self._shape("ftp://example.com/"))
        self.assertFalse(self._shape("http://"))


class tempfile_dirs:
    """Dua TemporaryDirectory (base + outside) sebagai context manager."""

    def __enter__(self):
        import tempfile

        self._ctx_base = tempfile.TemporaryDirectory()
        self._ctx_out = tempfile.TemporaryDirectory()
        return self._ctx_base.name, self._ctx_out.name

    def __exit__(self, *exc):
        self._ctx_out.cleanup()
        self._ctx_base.cleanup()
        return False


if __name__ == "__main__":
    unittest.main()
