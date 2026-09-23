"""Cost tracking per request: estimasi USD dari token + nama model.

Fitur roadmap: Cost tracking per request (log token & harga).
Cepat, tanpa LLM/infra — tablen harga & ekstraksi model diuji langsung.
"""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from src.core.observability import pricing
from src.core.observability.usage import _last_usage, note_usage, pop_usage


class TestEstimateCostUsd(unittest.TestCase):
    def test_known_model_arithmetic(self) -> None:
        # gpt-4o: $2.5/1M input, $10/1M output → 1M+1M tokens = 12.5
        self.assertEqual(pricing.estimate_cost_usd("gpt-4o", 1_000_000, 1_000_000), 12.5)

    def test_zero_tokens_zero_cost(self) -> None:
        self.assertEqual(pricing.estimate_cost_usd("gpt-4o", 0, 0), 0.0)

    def test_none_tokens_treated_as_zero(self) -> None:
        self.assertEqual(pricing.estimate_cost_usd("gpt-4o", None, None), 0.0)

    def test_unknown_model_without_env_fallback_zero(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COST_PER_1M_PROMPT", None)
            os.environ.pop("COST_PER_1M_COMPLETION", None)
            self.assertEqual(pricing.estimate_cost_usd("model-tak-dikenal", 100, 200), 0.0)

    def test_unknown_model_uses_env_fallback(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"COST_PER_1M_PROMPT": "1.0", "COST_PER_1M_COMPLETION": "2.0"},
            clear=False,
        ):
            # 500k prompt + 250k completion → 0.5 + 0.5 = 1.0
            self.assertEqual(pricing.estimate_cost_usd("model-tak-dikenal", 500_000, 250_000), 1.0)

    def test_register_model_price_override(self) -> None:
        pricing.register_model_price("custom-x", 1.0, 1.0)
        self.assertEqual(pricing.price_for("custom-x"), (1.0, 1.0))
        self.assertEqual(pricing.estimate_cost_usd("custom-x", 1_000_000, 0), 1.0)


class TestNoteUsageModelExtraction(unittest.TestCase):
    def tearDown(self) -> None:
        _last_usage.set({})

    def _fake(self, **kwargs) -> SimpleNamespace:
        return SimpleNamespace(**kwargs)

    def test_model_from_response_metadata(self) -> None:
        resp = self._fake(
            response_metadata={
                "model_name": "llama-3.3-70b-instruct",
                "token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }
        )
        note_usage(resp)
        self.assertEqual(pop_usage()["model"], "llama-3.3-70b-instruct")

    def test_model_from_attribute_fallback(self) -> None:
        resp = self._fake(response_metadata={}, model="gpt-4o-mini")
        note_usage(resp)
        self.assertEqual(pop_usage()["model"], "gpt-4o-mini")

    def test_usage_metadata_path_keeps_model(self) -> None:
        resp = self._fake(
            usage_metadata={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            response_metadata={"model_name": "deepseek-chat"},
        )
        note_usage(resp)
        data = pop_usage()
        self.assertEqual(data["prompt_tokens"], 10)
        self.assertEqual(data["completion_tokens"], 20)
        self.assertEqual(data["model"], "deepseek-chat")

    def test_no_usage_no_write(self) -> None:
        resp = self._fake(response_metadata={})
        note_usage(resp)
        self.assertEqual(pop_usage(), {})


if __name__ == "__main__":
    unittest.main()
