"""Multi-step planning: buat_plan/jalankan_langkah logic unit tests.

Fitur roadmap: Multi-step planning (#citizen).
Cepat, tanpa LLM/infra — test helper parsing, owner scoping, capability
registration, dan format output (lewat factory build() tanpa DB).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mcp_core.tool_validator import TOOL_CAPABILITIES
from src.plugins.core_tools import AVAILABLE_PLUGINS
from src.plugins.planning_tools import (
    _STEP_ICON,
    MAX_LANGKAH,
    _format_plan,
    _parse_langkah,
    _plan_user,
)
from tests import factories as f

PLANNING_TOOLS = {
    "buat_plan",
    "lihat_plan",
    "cari_plan",
    "jalankan_langkah",
    "tandai_selesai",
    "batal_plan",
}


class TestParseLangkah(unittest.TestCase):
    def test_split_by_line_and_strip_number_prefix(self) -> None:
        raw = "1. Analisis skema\n2) Buat migrasi\n3. Uji data"
        steps = _parse_langkah(raw)
        self.assertEqual(steps, ["Analisis skema", "Buat migrasi", "Uji data"])

    def test_skip_empty_lines(self) -> None:
        raw = "\n  \nLangkah A\n\nLangkah B\n"
        self.assertEqual(_parse_langkah(raw), ["Langkah A", "Langkah B"])

    def test_cap_length_per_step(self) -> None:
        long = "x" * 1000
        steps = _parse_langkah(long)
        self.assertLessEqual(len(steps[0]), 500)

    def test_empty_input(self) -> None:
        self.assertEqual(_parse_langkah("   "), [])


class TestPlanUser(unittest.TestCase):
    def test_fallback_anonymous_without_auth(self) -> None:
        self.assertEqual(_plan_user(), "anonymous")


class TestFormatPlan(unittest.TestCase):
    def test_format_marks_selesai_steps_with_hasil(self) -> None:
        plan = f.PlanFactory.build(status="aktif", judul="migrasi-db", tujuan="Pindah ke PostgreSQL")
        done = f.PlanStepFactory.build(urutan=1, status="selesai", deskripsi="Buat migrasi", hasil="OK")
        _steps = f.PlanStepFactory.build(urutan=2, status="pending", deskripsi="Uji data")
        out = _format_plan(plan, [done, _steps])
        self.assertIn("migrasi-db", out)
        self.assertIn("[OK]", out)
        self.assertIn("=> OK", out)
        self.assertIn("[?] Uji data", out)
        self.assertIn(f"ID: {plan.id}", out)


class TestCapabilitiesRegistration(unittest.TestCase):
    def test_all_agents_have_planning_tools(self) -> None:
        for agent in ("coder_agent", "admin_agent", "casual_agent"):
            caps = TOOL_CAPABILITIES.get(agent, set())
            self.assertTrue(PLANNING_TOOLS.issubset(caps), f"{agent} kurang tools: {PLANNING_TOOLS - caps}")

    def test_planning_tools_registered_in_plugins(self) -> None:
        for name in PLANNING_TOOLS:
            self.assertIn(name, AVAILABLE_PLUGINS, f"{name} tidak terdaftar di AVAILABLE_PLUGINS")

    def test_step_icon_covers_all_statuses(self) -> None:
        for status in ("pending", "berjalan", "selesai", "gagal"):
            self.assertIn(status, _STEP_ICON)

    def test_max_langkah_positive(self) -> None:
        self.assertGreater(MAX_LANGKAH, 0)
        self.assertLessEqual(MAX_LANGKAH, 20)


if __name__ == "__main__":
    unittest.main()
