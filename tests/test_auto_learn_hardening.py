"""Regression vuln-0005 — hardening auto-learn keyword (LLM poisoning).

Cakup:
- choke-point sanitize_keyword_tools (agent valid, allowed_tools ⊆ TOOL_CAPABILITIES)
- jalur immediate router narrow-only via filter_tool_names_for_agent
- auto_learn_keyword: proposal ke persetujuan owner, TANPA tulis global langsung
- keyword novel saja (tolak squatting/overwrite mapping yang sudah ada)
- tool learn_keyword menyaring allowed_tools sebelum persist
- _apply_learning_row: re-sanitize saat approve, fail-closed bila payload rusak
- docstring auth: default REQUIRE_API_KEY=1 (konsisten kode/dokumen)
"""

import inspect
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.config.routing_keywords_pg import sanitize_keyword_tools
from src.mcp_core.tool_validator import (
    TOOL_CAPABILITIES,
    filter_tool_names_for_agent,
    validate_tools_for_agent,
)


class TestSanitizeKeywordTools(unittest.TestCase):
    def test_agent_tak_dikenal_ditolak(self):
        self.assertIsNone(sanitize_keyword_tools("evil_agent", ["cari_web"]))

    def test_tool_luar_kapasitas_dibuang(self):
        self.assertEqual(
            sanitize_keyword_tools("casual_agent", ["tulis_kode", "get_current_time"]),
            ["get_current_time"],
        )

    def test_coder_tetap_dapat_tool_terlarang_lain(self):
        self.assertEqual(
            sanitize_keyword_tools("coder_agent", ["jalankan_python", "panggil_mcp"]),
            ["jalankan_python", "panggil_mcp"],
        )

    def test_tool_tak_dikenal_dibuang(self):
        self.assertEqual(sanitize_keyword_tools("coder_agent", ["format_disk"]), [])

    def test_list_kosong_valid(self):
        self.assertEqual(sanitize_keyword_tools("admin_agent", []), [])

    def test_duplikat_dihapus(self):
        self.assertEqual(
            sanitize_keyword_tools("coder_agent", ["baca_file", "baca_file"]),
            ["baca_file"],
        )


class TestFilterToolNamesForAgent(unittest.TestCase):
    def test_learned_path_narrow_only(self):
        self.assertEqual(
            filter_tool_names_for_agent("casual_agent", ["tulis_kode", "cari_web"]),
            [],
        )

    def test_coder_allowed(self):
        self.assertEqual(filter_tool_names_for_agent("coder_agent", ["tulis_kode"]), ["tulis_kode"])

    def test_unknown_agent_fail_closed(self):
        self.assertEqual(filter_tool_names_for_agent("ghost_agent", ["tulis_kode"]), [])

    def test_validate_tools_intersect(self):
        class T:
            def __init__(self, name):
                self.name = name

        out = validate_tools_for_agent("casual_agent", [T("tulis_kode"), T("get_current_time")])
        self.assertEqual([t.name for t in out], ["get_current_time"])

    def test_casual_tak_punya_tool_eksekusi(self):
        self.assertNotIn("jalankan_python", TOOL_CAPABILITIES["casual_agent"])
        self.assertNotIn("panggil_mcp", TOOL_CAPABILITIES["casual_agent"])
        self.assertNotIn("tulis_kode", TOOL_CAPABILITIES["casual_agent"])


class TestAutoLearnProposal(unittest.TestCase):
    @staticmethod
    def _llm(payload):
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content=json.dumps(payload))
        return llm

    @patch("src.config.routing_keywords_pg.add_keyword_with_tools")
    @patch("src.core.auth.approval.propose_learning", return_value="pid-1")
    @patch("src.config.routing_keywords_pg.get_routing_keywords_with_tools")
    @patch("src.core.llm.factory.get_llm")
    def test_propose_tanpa_tulis_global_langsung(self, mock_llm, mock_map, mock_propose, mock_add):
        mock_map.return_value = ({"coder_agent": ["kode"]}, "casual_agent")
        mock_llm.return_value = self._llm(
            {"agent": "admin_agent", "keyword": "cuaca bandung", "allowed_tools": ["cari_web"]}
        )
        from src.core.routing.intent import auto_learn_keyword

        out = auto_learn_keyword("cek cuaca bandung besok", "s1")
        self.assertEqual(out, ("admin_agent", "cuaca bandung", ["cari_web"]))
        mock_propose.assert_called_once()
        mock_add.assert_not_called()

    @patch("src.config.routing_keywords_pg.add_keyword_with_tools")
    @patch("src.core.auth.approval.propose_learning")
    @patch("src.config.routing_keywords_pg.get_routing_keywords_with_tools")
    @patch("src.core.llm.factory.get_llm")
    def test_keyword_squat_ditolak(self, mock_llm, mock_map, mock_propose, mock_add):
        mock_map.return_value = ({"coder_agent": ["kode"]}, "casual_agent")
        mock_llm.return_value = self._llm({"agent": "coder_agent", "keyword": "kode", "allowed_tools": ["tulis_kode"]})
        from src.core.routing.intent import auto_learn_keyword

        out = auto_learn_keyword("kode python dong", "s1")
        self.assertIsNone(out)
        mock_propose.assert_not_called()
        mock_add.assert_not_called()

    @patch("src.config.routing_keywords_pg.add_keyword_with_tools")
    @patch("src.core.auth.approval.propose_learning", return_value="pid-2")
    @patch("src.config.routing_keywords_pg.get_routing_keywords_with_tools")
    @patch("src.core.llm.factory.get_llm")
    def test_output_llm_disaring_ke_kapasitas_agent(self, mock_llm, mock_map, mock_propose, mock_add):
        mock_map.return_value = ({"coder_agent": ["kode"]}, "casual_agent")
        mock_llm.return_value = self._llm(
            {
                "agent": "casual_agent",
                "keyword": "mode diam",
                "allowed_tools": ["jalankan_python", "panggil_mcp", "get_current_time"],
            }
        )
        from src.core.routing.intent import auto_learn_keyword

        out = auto_learn_keyword("aktifkan mode diam ya", "s1")
        self.assertEqual(out, ("casual_agent", "mode diam", ["get_current_time"]))
        mock_propose.assert_called_once()


class TestLearnKeywordTool(unittest.TestCase):
    @patch("src.config.routing_keywords_pg.invalidate_routing_cache")
    @patch("src.config.routing_keywords_pg.add_keyword_with_tools", return_value=True)
    def test_allowed_tools_disaring_sebelum_persist(self, mock_add, _inv):
        from src.plugins.web_tools import learn_keyword

        out = learn_keyword.invoke(
            {
                "agent": "admin_agent",
                "keyword": "dolar hari ini",
                "allowed_tools": "cari_web,tulis_kode,jalankan_python",
            }
        )
        mock_add.assert_called_once_with("admin_agent", "dolar hari ini", ["cari_web"])
        self.assertIn("ditolak", out)


class TestApplyLearningRow(unittest.TestCase):
    @patch("src.core.auth.audit.append_audit")
    @patch("src.config.routing_keywords_pg.invalidate_routing_cache")
    @patch("src.config.routing_keywords_pg.add_keyword_with_tools", return_value=True)
    def test_apply_re_sanitize(self, mock_add, _inv, _audit):
        from src.core.auth.approval import _apply_learning_row

        pa = SimpleNamespace(
            id="x",
            args=json.dumps({"agent": "casual_agent", "keyword": "halo dunia", "allowed_tools": ["tulis_kode"]}),
        )
        self.assertTrue(_apply_learning_row(pa, actor="u1"))
        mock_add.assert_called_once_with("casual_agent", "halo dunia", [])

    @patch("src.config.routing_keywords_pg.add_keyword_with_tools")
    def test_apply_agent_palsu_ditolak(self, mock_add):
        from src.core.auth.approval import _apply_learning_row

        pa = SimpleNamespace(
            id="x",
            args=json.dumps({"agent": "root_agent", "keyword": "x y", "allowed_tools": []}),
        )
        self.assertFalse(_apply_learning_row(pa, actor="u1"))
        mock_add.assert_not_called()

    @patch("src.config.routing_keywords_pg.add_keyword_with_tools")
    def test_apply_args_rusak_ditolak(self, mock_add):
        from src.core.auth.approval import _apply_learning_row

        pa = SimpleNamespace(id="x", args="{tidak-valid-json")
        self.assertFalse(_apply_learning_row(pa, actor="u1"))
        mock_add.assert_not_called()


class TestAuthDocstringConsistency(unittest.TestCase):
    def test_default_auth_dinyatakan_on(self):
        import src.core.auth.auth as auth_mod

        src = inspect.getsource(auth_mod)
        self.assertNotIn("Bila mati (default)", src)
        self.assertIn("REQUIRE_API_KEY=0", src)
        self.assertIn("fail-closed", src)


if __name__ == "__main__":
    unittest.main()
