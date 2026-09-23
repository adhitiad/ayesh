"""Tool versioning: registry `nama@vN`, resolusi default, wiring routing/karantina.

Fitur roadmap: Tool versioning (tool@v1, tool@v2 untuk kompatibilitas).
Cepat, tanpa LLM/infra — registrasi pakai stub ber-`.name`, bukan LangChain.
"""

import unittest
from typing import Any, ClassVar

from src.mcp_core import versioning


class _Tool:
    def __init__(self, name: str, marker: str) -> None:
        self.name = name
        self.marker = marker


class _Stub:
    """Isolasi registry per-test agar test tidak saling mengganggu."""

    def setUp(self) -> None:
        self._backup = dict(versioning._registry._versions)
        self._backup_defaults = dict(versioning._registry._defaults)
        versioning._registry._versions.clear()
        versioning._registry._defaults.clear()

    def tearDown(self) -> None:
        versioning._registry._versions.clear()
        versioning._registry._defaults.update(self._backup_defaults)
        versioning._registry._versions.update(self._backup)


class TestNormalize(_Stub, unittest.TestCase):
    def test_strips_version_suffix(self) -> None:
        self.assertEqual(versioning.normalize("office_tool@v1"), "office_tool")
        self.assertEqual(versioning.normalize("cari_web@v2"), "cari_web")

    def test_without_suffix_unchanged(self) -> None:
        self.assertEqual(versioning.normalize("cari_web"), "cari_web")

    def test_unknown_format_unchanged(self) -> None:
        self.assertEqual(versioning.normalize("weird@v2.5"), "weird@v2.5")


class TestRegistration(_Stub, unittest.TestCase):
    def test_plain_name_resolves_to_default_latest(self) -> None:
        v1, v2 = _Tool("demo", "v1"), _Tool("demo", "v2")
        versioning.register("demo", v1, version=1)
        versioning.register("demo", v2, version=2)
        self.assertIs(versioning.lookup("demo"), v2)
        self.assertEqual(versioning.default_version("demo"), 2)

    def test_explicit_old_version_still_callable(self) -> None:
        v1, v2 = _Tool("demo", "v1"), _Tool("demo", "v2")
        versioning.register("demo", v1, version=1)
        versioning.register("demo", v2, version=2)
        self.assertIs(versioning.lookup("demo@v1"), v1)
        self.assertIs(versioning.lookup("demo@v2"), v2)

    def test_unknown_version_falls_back_to_default(self) -> None:
        v1, v2 = _Tool("demo", "v1"), _Tool("demo", "v2")
        versioning.register("demo", v1, version=1)
        versioning.register("demo", v2, version=2)
        self.assertIs(versioning.lookup("demo@v99"), v2)

    def test_unknown_tool_returns_none(self) -> None:
        self.assertIsNone(versioning.lookup("nope"))
        self.assertIsNone(versioning.lookup("nope@v1"))
        self.assertFalse(versioning.supports("nope"))

    def test_register_ignores_suffix_in_base_name(self) -> None:
        obj = _Tool("x", "m")
        versioning.register("x@v3", obj, version=3)
        self.assertEqual(versioning.default_version("x"), 3)
        self.assertIs(versioning.lookup("x@v3"), obj)
        self.assertEqual(versioning.list_versions("x"), [3])

    def test_version_below_one_clamped(self) -> None:
        obj = _Tool("y", "m")
        versioning.register("y", obj, version=0)
        self.assertEqual(versioning.list_versions("y"), [1])
        self.assertEqual(versioning.default_version("y"), 1)


class TestHelpers(_Stub, unittest.TestCase):
    def test_tools_from_names_resolves_aliases_and_skips_unknown(self) -> None:
        v1, v2 = _Tool("demo", "v1"), _Tool("demo", "v2")
        versioning.register("demo", v1, version=1)
        versioning.register("demo", v2, version=2)
        tools = versioning.tools_from_names(["demo@v1", "nope", "demo"])
        self.assertEqual([t.marker for t in tools], ["v1", "v2"])

    def test_resolve_tool_references_canonical_unique_sorted(self) -> None:
        refs = versioning.resolve_tool_references(["cari_web", "baca_file@v2", "cari_web@v1", "BACA"])
        self.assertEqual(refs, ["BACA", "baca_file", "cari_web"])


class TestCorePluginsRegistered(unittest.TestCase):
    """Pada import core_tools (lazy), semua plugin otomatis ter-registrasi."""

    _plugins: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        from src.plugins.core_tools import AVAILABLE_PLUGINS

        cls._plugins = AVAILABLE_PLUGINS

    def test_all_plugins_registered_as_v1(self) -> None:
        for name in self._plugins:
            self.assertTrue(versioning.supports(name), f"{name} belum terdaftar")
            self.assertEqual(versioning.default_version(name), 1, f"{name} bukan v1")

    def test_versioned_alias_resolves_to_same_impl(self) -> None:
        self.assertIs(versioning.lookup("tulis_kode@v1"), self._plugins["tulis_kode"])
        self.assertIs(versioning.lookup("baca_file@v1"), self._plugins["baca_file"])

    def test_unknown_version_still_falls_back(self) -> None:
        self.assertIs(versioning.lookup("office_tool@v99"), self._plugins["office_tool"])


if __name__ == "__main__":
    unittest.main()
