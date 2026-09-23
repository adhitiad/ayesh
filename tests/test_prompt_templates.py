"""Prompt template library: render placeholder, register kustom, list bawaan.

Fitur roadmap: Prompt template library (simpan & reuse prompt).
Cepat, tanpa LLM/infra — murni fungsi registry + render.
"""

import unittest

from src.core.llm import templates


class TestTemplateLibrary(unittest.TestCase):
    def setUp(self) -> None:
        templates.reset_templates()

    def test_builtin_renders(self) -> None:
        out = templates.render("ringkas", max_kata="50", bahasa="Indonesia", teks="halo dunia")
        self.assertIn("50", out)
        self.assertIn("halo dunia", out)

    def test_missing_placeholder_preserved(self) -> None:
        out = templates.render("terjemah", teks="halo dunia")
        self.assertIn("{bahasa}", out)

    def test_unknown_template_raises(self) -> None:
        with self.assertRaises(KeyError):
            templates.render("tidak-ada")

    def test_get_template_none_for_unknown(self) -> None:
        self.assertIsNone(templates.get_template("tidak-ada"))

    def test_register_custom_and_overwrite(self) -> None:
        templates.register_template("custom", "Halo {nama}")
        self.assertEqual(templates.render("custom", nama="Ayesh"), "Halo Ayesh")
        templates.register_template("custom", "Revisi {nama}")
        self.assertEqual(templates.render("custom", nama="Budi"), "Revisi Budi")

    def test_register_empty_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            templates.register_template("  ", "isi")

    def test_list_contains_builtins_and_custom(self) -> None:
        templates.register_template("custom-a", "x")
        names = templates.list_templates()
        for builtin in ("ringkas", "surat_resmi", "intent", "kode_review", "terjemah"):
            self.assertIn(builtin, names)
        self.assertIn("custom-a", names)
        self.assertEqual(names, sorted(names))

    def test_reset_restores_vanilla(self) -> None:
        templates.register_template("tmp", "x")
        templates.reset_templates()
        self.assertIsNone(templates.get_template("tmp"))
        self.assertIsNotNone(templates.get_template("ringkas"))


if __name__ == "__main__":
    unittest.main()
