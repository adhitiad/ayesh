import os
import unittest
from unittest import mock

from src.core.llm import task_routing as tr


class TestClassifyTask(unittest.TestCase):
    def tearDown(self):
        tr.reset_for_tests()

    def test_agent_mapping(self):
        self.assertEqual(tr.classify_task("coder_agent"), "code")
        self.assertEqual(tr.classify_task("admin_agent"), "admin")
        self.assertEqual(tr.classify_task("casual_agent"), "chat")

    def test_keyword_override(self):
        self.assertEqual(tr.classify_task("casual_agent", "tolong ringkas artikel ini"), "summarize")
        self.assertEqual(tr.classify_task("coder_agent", "buat_plan rilis"), "plan")

    def test_unknown_agent_defaults_chat(self):
        self.assertEqual(tr.classify_task(None), "chat")
        self.assertEqual(tr.classify_task("unknown_agent"), "chat")

    def test_each_keyword_alias(self):
        cases = [
            ("ringkas", "summarize"),
            ("summary", "summarize"),
            ("summarize", "summarize"),
            ("buat_plan", "plan"),
            ("rencana", "plan"),
            ("planning", "plan"),
        ]
        for text, want in cases:
            with self.subTest(text=text):
                self.assertEqual(tr.classify_task(None, text), want)


class TestEnabled(unittest.TestCase):
    def test_truthy_values(self):
        for val in ("1", "true", "yes"):
            with (
                self.subTest(val=val),
                mock.patch.dict(os.environ, {"MODEL_ROUTING_ENABLED": val}, clear=False),
            ):
                self.assertTrue(tr._enabled())

    def test_falsy_values(self):
        for val in ("0", "", "no", "garbage"):
            with (
                self.subTest(val=val),
                mock.patch.dict(os.environ, {"MODEL_ROUTING_ENABLED": val}, clear=False),
            ):
                self.assertFalse(tr._enabled())


class TestInitTaskProvider(unittest.TestCase):
    def test_build_config_none_returns_none(self):
        with mock.patch("src.core.llm.factory._build_config", return_value=None):
            self.assertIsNone(tr._init_task_provider("deepseek", "m"))

    def test_success_sets_model_and_creates(self):
        config = mock.Mock()
        prov = mock.Mock()
        prov.create.return_value = "LLM"
        with (
            mock.patch("src.core.llm.factory._build_config", return_value=config),
            mock.patch("src.core.llm.factory.ProviderRegistry.get", return_value=prov) as g,
        ):
            out = tr._init_task_provider("deepseek", "deepseek-chat")
        self.assertEqual(out, "LLM")
        self.assertEqual(config.model, "deepseek-chat")
        g.assert_called_once_with("deepseek")
        prov.create.assert_called_once_with(config)

    def test_unknown_provider_returns_none(self):
        config = mock.Mock()
        with (
            mock.patch("src.core.llm.factory._build_config", return_value=config),
            mock.patch("src.core.llm.factory.ProviderRegistry.get", return_value=None),
        ):
            self.assertIsNone(tr._init_task_provider("nope", None))

    def test_create_error_returns_none(self):
        config = mock.Mock()
        prov = mock.Mock()
        prov.create.side_effect = RuntimeError("boom")
        with (
            mock.patch("src.core.llm.factory._build_config", return_value=config),
            mock.patch("src.core.llm.factory.ProviderRegistry.get", return_value=prov),
        ):
            self.assertIsNone(tr._init_task_provider("deepseek", "m"))


class TestResolveRoute(unittest.TestCase):
    def tearDown(self):
        tr.reset_for_tests()

    def test_disabled_returns_none(self):
        with mock.patch.dict(os.environ, {"MODEL_ROUTING_ENABLED": "0"}, clear=False):
            self.assertIsNone(tr.resolve_route("code"))

    def test_enabled_parse_provider_model(self):
        env = {"MODEL_ROUTING_ENABLED": "1", "MODEL_ROUTE_CODE": "deepseek:deepseek-chat"}
        with mock.patch.dict(os.environ, env, clear=False):
            route = tr.resolve_route("code")
        self.assertEqual(route, ("deepseek", "deepseek-chat"))

    def test_enabled_provider_only(self):
        env = {"MODEL_ROUTING_ENABLED": "1", "MODEL_ROUTE_CHAT": "groq"}
        with mock.patch.dict(os.environ, env, clear=False):
            route = tr.resolve_route("chat")
        self.assertEqual(route, ("groq", None))

    def test_unset_task_returns_none(self):
        env = {"MODEL_ROUTING_ENABLED": "1"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("MODEL_ROUTE_CODE", None)
            self.assertIsNone(tr.resolve_route("code"))


class TestGetLlmForTask(unittest.TestCase):
    def tearDown(self):
        tr.reset_for_tests()

    def test_disabled_falls_back_to_get_llm(self):
        sentinel = object()
        with (
            mock.patch.dict(os.environ, {"MODEL_ROUTING_ENABLED": "0"}, clear=False),
            mock.patch("src.core.llm.factory.get_llm", return_value=sentinel),
        ):
            self.assertIs(tr.get_llm_for_task("code"), sentinel)

    def test_resolve_none_falls_back(self):
        sentinel = object()
        env = {"MODEL_ROUTING_ENABLED": "1"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("MODEL_ROUTE_CODE", None)
            with mock.patch("src.core.llm.factory.get_llm", return_value=sentinel):
                self.assertIs(tr.get_llm_for_task("code"), sentinel)

    def test_init_fail_falls_back(self):
        sentinel = object()
        env = {"MODEL_ROUTING_ENABLED": "1", "MODEL_ROUTE_CODE": "deepseek:deepseek-chat"}
        with (
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch.object(tr, "_init_task_provider", return_value=None),
            mock.patch("src.core.llm.factory.get_llm", return_value=sentinel),
        ):
            self.assertIs(tr.get_llm_for_task("code"), sentinel)

    def test_success_caches_instance(self):
        inst = object()
        env = {"MODEL_ROUTING_ENABLED": "1", "MODEL_ROUTE_CODE": "deepseek:deepseek-chat"}
        with (
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch.object(tr, "_init_task_provider", return_value=inst) as m,
        ):
            first = tr.get_llm_for_task("code")
            second = tr.get_llm_for_task("code")
        self.assertIs(first, inst)
        self.assertIs(second, inst)
        self.assertEqual(m.call_count, 1)

    def test_cache_key_format(self):
        inst = object()
        env = {"MODEL_ROUTING_ENABLED": "1", "MODEL_ROUTE_CODE": "deepseek:deepseek-chat"}
        with (
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch.object(tr, "_init_task_provider", return_value=inst),
        ):
            tr.get_llm_for_task("code")
        self.assertIn("deepseek:deepseek-chat", tr._task_cache)

    def test_cache_key_provider_only_route(self):
        inst = object()
        env = {"MODEL_ROUTING_ENABLED": "1", "MODEL_ROUTE_CHAT": "groq"}
        with (
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch.object(tr, "_init_task_provider", return_value=inst),
        ):
            tr.get_llm_for_task("chat")
        self.assertIn("groq:", tr._task_cache)


if __name__ == "__main__":
    unittest.main()
