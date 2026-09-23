import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.mcp_core.tool_validator import TOOL_CAPABILITIES
from src.plugins import marketplace as mp

# Sumber tool palsu: cukup punya .name + callable .func (lolos _collect_tools)
# tanpa import langchain.
_FAKE_TOOL = (
    "class _T: pass\n"
    "contoh_tool_xyz = _T()\n"
    "contoh_tool_xyz.name = 'contoh_tool_xyz'\n"
    "contoh_tool_xyz.func = lambda teks: teks\n"
)


class MarketplaceTestCase(unittest.TestCase):
    """Setup: root marketplace di tmp, plugin dict & audit di-patch, caps di-snapshot."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ayesh_mkt_"))
        self.plugins: dict = {}
        self._patchers = [
            mock.patch.object(mp, "_ROOT", self.tmp),
            mock.patch.object(mp, "_get_plugins", return_value=self.plugins),
            mock.patch.object(mp, "_audit"),
        ]
        started = [p.start() for p in self._patchers]
        self.audit = started[2]
        self._caps_snapshot = {k: set(v) for k, v in TOOL_CAPABILITIES.items()}
        (self.tmp / "tools").mkdir(parents=True)
        self.src = self.tmp / "tools" / "contoh_tool_xyz.py"
        self.src.write_text(_FAKE_TOOL, encoding="utf-8")
        self.sha = hashlib.sha256(self.src.read_bytes()).hexdigest()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        TOOL_CAPABILITIES.clear()
        TOOL_CAPABILITIES.update({k: set(v) for k, v in self._caps_snapshot.items()})
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_registry(self, entries: list) -> None:
        (self.tmp / "index.json").write_text(json.dumps({"tools": entries}), encoding="utf-8")

    def valid_entry(self, **over) -> dict:
        entry = {
            "name": "contoh_tool_xyz",
            "version": "1.0.0",
            "description": "contoh",
            "source": "tools/contoh_tool_xyz.py",
            "sha256": self.sha,
            "agents": ["casual_agent"],
        }
        entry.update(over)
        return entry


class TestRegistryValidation(MarketplaceTestCase):
    def test_valid_entry_loaded(self):
        self.write_registry([self.valid_entry()])
        reg = mp.load_registry()
        self.assertIn("contoh_tool_xyz", reg)
        self.assertEqual(reg["contoh_tool_xyz"]["sha256"], self.sha)

    def test_invalid_entries_dropped_fail_closed(self):
        self.write_registry(
            [
                self.valid_entry(),
                self.valid_entry(name="../evil"),
                self.valid_entry(sha256="bukan-hash"),
                self.valid_entry(source="../../etc/passwd"),
                self.valid_entry(source="/abs/path.py"),
                self.valid_entry(agents=["unknown_agent"]),
                self.valid_entry(name="BadName"),
            ]
        )
        self.assertEqual(list(mp.load_registry()), ["contoh_tool_xyz"])

    def test_missing_or_broken_registry_returns_empty(self):
        self.assertEqual(mp.load_registry(), {})
        (self.tmp / "index.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(mp.load_registry(), {})


class TestInstall(MarketplaceTestCase):
    def test_happy_path(self):
        self.write_registry([self.valid_entry()])
        out = mp.install_tool("contoh_tool_xyz", actor="admin1")
        self.assertTrue(out["installed"])
        self.assertTrue((self.tmp / "installed" / "contoh_tool_xyz.py").is_file())
        self.assertTrue((self.tmp / "installed" / "contoh_tool_xyz.json").is_file())
        self.assertIn("contoh_tool_xyz", self.plugins)
        self.assertIn("contoh_tool_xyz", TOOL_CAPABILITIES["casual_agent"])
        self.audit.assert_called_once()
        self.assertTrue(mp.list_marketplace()[0]["installed"])

    def test_hash_mismatch_denied(self):
        self.write_registry([self.valid_entry(sha256="0" * 64)])
        with self.assertRaises(mp.MarketplaceError) as ctx:
            mp.install_tool("contoh_tool_xyz")
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(ctx.exception.code, "HASH_MISMATCH")
        self.assertFalse((self.tmp / "installed").exists())
        self.assertEqual(self.plugins, {})

    def test_bad_names_denied(self):
        for bad in ("../evil", "Nama", "", "a" * 65, "a/b"):
            with self.subTest(name=bad), self.assertRaises(mp.MarketplaceError) as ctx:
                mp.install_tool(bad)
            self.assertEqual(ctx.exception.status, 400)

    def test_unknown_tool_404(self):
        self.write_registry([self.valid_entry()])
        with self.assertRaises(mp.MarketplaceError) as ctx:
            mp.install_tool("tidak_ada")
        self.assertEqual(ctx.exception.status, 404)

    def test_duplicate_tool_denied(self):
        self.write_registry([self.valid_entry()])
        self.plugins["contoh_tool_xyz"] = object()
        with self.assertRaises(mp.MarketplaceError) as ctx:
            mp.install_tool("contoh_tool_xyz")
        self.assertEqual(ctx.exception.code, "DUPLICATE_TOOL")
        self.assertFalse((self.tmp / "installed" / "contoh_tool_xyz.py").exists())

    def test_module_without_tools_denied(self):
        self.src.write_text("x = 1\n", encoding="utf-8")
        entry = self.valid_entry(sha256=hashlib.sha256(self.src.read_bytes()).hexdigest())
        self.write_registry([entry])
        with self.assertRaises(mp.MarketplaceError) as ctx:
            mp.install_tool("contoh_tool_xyz")
        self.assertEqual(ctx.exception.code, "NO_TOOLS")

    def test_audit_failure_rolls_back(self):
        self.write_registry([self.valid_entry()])
        self.audit.side_effect = RuntimeError("db down")
        with self.assertRaises(mp.MarketplaceError) as ctx:
            mp.install_tool("contoh_tool_xyz")
        self.assertEqual(ctx.exception.status, 500)
        self.assertFalse((self.tmp / "installed" / "contoh_tool_xyz.py").exists())
        self.assertEqual(self.plugins, {})
        self.assertNotIn("contoh_tool_xyz", TOOL_CAPABILITIES["casual_agent"])


class TestUninstall(MarketplaceTestCase):
    def test_uninstall_revokes_everything(self):
        self.write_registry([self.valid_entry()])
        mp.install_tool("contoh_tool_xyz")
        self.audit.reset_mock()
        out = mp.uninstall_tool("contoh_tool_xyz", actor="admin1")
        self.assertTrue(out["uninstalled"])
        self.assertFalse((self.tmp / "installed" / "contoh_tool_xyz.py").exists())
        self.assertNotIn("contoh_tool_xyz", self.plugins)
        self.assertNotIn("contoh_tool_xyz", TOOL_CAPABILITIES["casual_agent"])
        self.audit.assert_called_once()
        with self.assertRaises(mp.MarketplaceError) as ctx:
            mp.uninstall_tool("contoh_tool_xyz")
        self.assertEqual(ctx.exception.status, 404)

    def test_uninstall_audit_failure_rolls_back(self):
        self.write_registry([self.valid_entry()])
        mp.install_tool("contoh_tool_xyz")
        self.audit.side_effect = RuntimeError("db down")
        with self.assertRaises(mp.MarketplaceError):
            mp.uninstall_tool("contoh_tool_xyz")
        self.assertTrue((self.tmp / "installed" / "contoh_tool_xyz.py").is_file())
        self.assertIn("contoh_tool_xyz", self.plugins)
        self.assertIn("contoh_tool_xyz", TOOL_CAPABILITIES["casual_agent"])


class TestStartupLoad(MarketplaceTestCase):
    def test_load_installed_skips_broken_module(self):
        inst = self.tmp / "installed"
        inst.mkdir(parents=True)
        (inst / "broken.py").write_text("raise RuntimeError('rusak')\n", encoding="utf-8")
        self.assertEqual(mp.load_installed(), {})

    def test_load_installed_returns_tools(self):
        self.write_registry([self.valid_entry()])
        mp.install_tool("contoh_tool_xyz")
        loaded = mp.load_installed()
        self.assertIn("contoh_tool_xyz", loaded)


class TestRoutesWiring(unittest.TestCase):
    def test_router_paths_registered(self):
        from src.api.routes_marketplace import router

        paths = {getattr(r, "path", "") for r in router.routes}
        self.assertIn("/marketplace", paths)
        self.assertIn("/marketplace/{name}/install", paths)
        self.assertIn("/marketplace/{name}", paths)


if __name__ == "__main__":
    unittest.main()
