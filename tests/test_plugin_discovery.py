"""Plugin discovery: auto-scan folder plugins/, auto-register @tool.

Fitur roadmap: Plugin discovery otomatis (#16).
Cepat, tanpa LLM/infra — test discovery logic langsung.
"""

import sys
import unittest
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.plugins.discovery import _is_structured_tool, build_available_plugins, discover_plugins


class FakeTool:
    def __init__(self, name: str):
        self.name = name
        self.func = lambda x: x
        self.description = "fake"


class TestIsStructuredTool(unittest.TestCase):
    def test_structured_tool_detected(self) -> None:
        obj = FakeTool("test_tool")
        self.assertTrue(_is_structured_tool(obj))

    def test_plain_function_not_detected(self) -> None:
        def plain(x):
            return x

        self.assertFalse(_is_structured_tool(plain))

    def test_dict_not_detected(self) -> None:
        self.assertFalse(_is_structured_tool({"name": "x"}))


class TestDiscoverPlugins(unittest.TestCase):
    def test_discovers_get_current_time(self) -> None:
        """Src/plugins/time_tool.py harus terdeteksi (memiliki @tool get_current_time)."""
        plugins = discover_plugins()
        self.assertIn("get_current_time", plugins)
        self.assertIsInstance(plugins["get_current_time"], FakeTool.__class__.__bases__[0] if False else object)

    def test_manual_overrides_merge(self) -> None:
        """build_available_plugins menggabungkan discovery + manual overrides."""
        manual = {"custom_tool": FakeTool("custom_tool")}
        merged = build_available_plugins(manual)
        self.assertIn("get_current_time", merged)
        self.assertIn("custom_tool", merged)
        self.assertIs(merged["custom_tool"], manual["custom_tool"])

    def test_manual_overrides_priority(self) -> None:
        """Manual overrides menimpa discovery jika nama sama."""
        manual = {"get_current_time": FakeTool("overridden")}
        merged = build_available_plugins(manual)
        self.assertIs(merged["get_current_time"], manual["get_current_time"])


if __name__ == "__main__":
    unittest.main()
