"""Tests for src.memory.summarizer — configurable summarization.

Covers SummaryConfig, hierarchical summarization, and integration with
OptimizedHybridMemory. All tests mock the DB and LLM to avoid real infra.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from src.memory.summarizer import (
    SummaryConfig,
    _hierarchical_summarize,
    _summarize_chunk,
    _summarize_final,
    get_summary_config,
    summarize_session,
    update_summary_config,
)


class TestSummaryConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = SummaryConfig()
        self.assertEqual(cfg.threshold, 20)
        self.assertEqual(cfg.keep_recent, 5)
        self.assertEqual(cfg.chunk_size, 10)
        self.assertTrue(cfg.hierarchical)
        self.assertEqual(cfg.max_levels, 3)

    def test_from_json_valid(self):
        raw = json.dumps(
            {
                "summary": {
                    "threshold": 10,
                    "keep_recent": 3,
                    "chunk_size": 5,
                    "hierarchical": False,
                    "max_levels": 2,
                }
            }
        )
        cfg = SummaryConfig.from_json(raw)
        self.assertEqual(cfg.threshold, 10)
        self.assertEqual(cfg.keep_recent, 3)
        self.assertEqual(cfg.chunk_size, 5)
        self.assertFalse(cfg.hierarchical)
        self.assertEqual(cfg.max_levels, 2)

    def test_from_json_partial(self):
        raw = json.dumps({"summary": {"threshold": 15}})
        cfg = SummaryConfig.from_json(raw)
        self.assertEqual(cfg.threshold, 15)
        self.assertEqual(cfg.keep_recent, 5)
        self.assertTrue(cfg.hierarchical)

    def test_from_json_none(self):
        cfg = SummaryConfig.from_json(None)
        self.assertEqual(cfg.threshold, 20)

    def test_from_json_empty(self):
        cfg = SummaryConfig.from_json("")
        self.assertEqual(cfg.threshold, 20)

    def test_from_json_invalid(self):
        cfg = SummaryConfig.from_json("not json")
        self.assertEqual(cfg.threshold, 20)

    def test_from_json_not_summary_key(self):
        cfg = SummaryConfig.from_json(json.dumps({"other": "data"}))
        self.assertEqual(cfg.threshold, 20)

    def test_to_context_dict(self):
        cfg = SummaryConfig(threshold=15, keep_recent=2, chunk_size=7)
        d = cfg.to_context_dict()
        self.assertIn("summary", d)
        self.assertEqual(d["summary"]["threshold"], 15)
        self.assertEqual(d["summary"]["keep_recent"], 2)
        self.assertEqual(d["summary"]["chunk_size"], 7)


class TestSummarizeChunk(unittest.TestCase):
    @patch("src.memory.summarizer.get_llm")
    def test_basic(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Topik A dibahas.")
        mock_get_llm.return_value = mock_llm
        result = _summarize_chunk(["user: halo", "assistant: halo juga"])
        self.assertEqual(result, "Topik A dibahas.")
        mock_llm.invoke.assert_called_once()

    @patch("src.memory.summarizer.get_llm")
    def test_empty_list(self, mock_get_llm):
        result = _summarize_chunk([])
        self.assertEqual(result, "")
        mock_get_llm.assert_not_called()

    @patch("src.memory.summarizer.get_llm")
    def test_whitespace_only(self, mock_get_llm):
        result = _summarize_chunk(["", "  "])
        self.assertEqual(result, "")
        mock_get_llm.assert_not_called()


class TestSummarizeFinal(unittest.TestCase):
    @patch("src.memory.summarizer.get_llm")
    def test_basic(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Ringkasan lengkap.")
        mock_get_llm.return_value = mock_llm
        result = _summarize_final(["ringkasan 1", "ringkasan 2"])
        self.assertEqual(result, "Ringkasan lengkap.")


class TestHierarchicalSummarize(unittest.TestCase):
    @patch("src.memory.summarizer.get_llm")
    def test_single_chunk(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Ringkasan chunk.")
        mock_get_llm.return_value = mock_llm
        msgs = [MagicMock(role="user", content="msg1")]
        cfg = SummaryConfig(chunk_size=10)
        result = _hierarchical_summarize(msgs, cfg)
        self.assertEqual(result, "Ringkasan chunk.")

    @patch("src.memory.summarizer.get_llm")
    def test_multiple_chunks_two_levels(self, mock_get_llm):
        call_count = [0]

        def side_effect(prompt):
            call_count[0] += 1
            if call_count[0] <= 3:
                return MagicMock(content=f"Chunk {call_count[0]} ringkas")
            return MagicMock(content="Final ringkasan")

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = side_effect
        mock_get_llm.return_value = mock_llm
        msgs = [MagicMock(role="user", content=f"msg{i}") for i in range(12)]
        cfg = SummaryConfig(chunk_size=4, max_levels=3)
        result = _hierarchical_summarize(msgs, cfg)
        self.assertIn("ringkas", result)
        self.assertTrue(call_count[0] >= 3)


class TestGetSummaryConfig(unittest.TestCase):
    @patch("src.memory.summarizer.SessionLocal")
    def test_with_context(self, mock_sessionmaker):
        mock_db = MagicMock()
        mock_sessionmaker.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_sessionmaker.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.execute.return_value.scalar.return_value = json.dumps({"summary": {"threshold": 12}})
        cfg = get_summary_config("sess1")
        self.assertEqual(cfg.threshold, 12)

    @patch("src.memory.summarizer.SessionLocal")
    def test_without_context(self, mock_sessionmaker):
        mock_db = MagicMock()
        mock_sessionmaker.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_sessionmaker.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.execute.return_value.scalar.return_value = None
        cfg = get_summary_config("sess1")
        self.assertEqual(cfg.threshold, 20)


class TestUpdateSummaryConfig(unittest.TestCase):
    @patch("src.memory.summarizer.SessionLocal")
    def test_update_creates(self, mock_sessionmaker):
        mock_db = MagicMock()
        mock_sessionmaker.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_sessionmaker.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.execute.return_value.scalar.return_value = None
        new_cfg = SummaryConfig(threshold=8)
        update_summary_config("sess1", new_cfg)
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()

    @patch("src.memory.summarizer.SessionLocal")
    def test_update_merges(self, mock_sessionmaker):
        mock_db = MagicMock()
        mock_sessionmaker.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_sessionmaker.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.execute.return_value.scalar.return_value = json.dumps(
            {"summary": {"threshold": 10}, "other_key": "keep"}
        )
        new_cfg = SummaryConfig(keep_recent=3)
        update_summary_config("sess1", new_cfg)
        mock_db.execute.assert_called()


class TestSummarizeSession(unittest.TestCase):
    @patch("src.memory.summarizer._hierarchical_summarize")
    @patch("src.memory.summarizer.SessionLocal")
    def test_below_threshold_skips(self, mock_sessionmaker, mock_hier):
        mock_db = MagicMock()
        mock_sessionmaker.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_sessionmaker.return_value.__exit__ = MagicMock(return_value=False)
        mock_results = [MagicMock(content=f"msg{i}") for i in range(5)]
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_results
        cfg = SummaryConfig(threshold=20)
        result = summarize_session("sess1", config=cfg)
        self.assertEqual(result, "")
        mock_hier.assert_not_called()

    @patch("src.memory.summarizer._hierarchical_summarize")
    @patch("src.memory.summarizer.SessionLocal")
    def test_above_threshold_summarizes(self, mock_sessionmaker, mock_hier):
        mock_db = MagicMock()
        mock_sessionmaker.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_sessionmaker.return_value.__exit__ = MagicMock(return_value=False)
        mock_msgs = [MagicMock(role="user", content=f"msg{i}") for i in range(15)]
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_msgs
        mock_hier.return_value = "Ringkasan test"
        cfg = SummaryConfig(threshold=10, keep_recent=5)
        result = summarize_session("sess1", config=cfg)
        self.assertEqual(result, "Ringkasan test")
        self.assertEqual(mock_db.execute.call_count, 2)


class TestUpdateSummaryConfigIntegration(unittest.TestCase):
    def test_roundtrip(self):
        cfg1 = SummaryConfig(threshold=8, keep_recent=2, chunk_size=4)
        raw = json.dumps(cfg1.to_context_dict())
        cfg2 = SummaryConfig.from_json(raw)
        self.assertEqual(cfg1.threshold, cfg2.threshold)
        self.assertEqual(cfg1.keep_recent, cfg2.keep_recent)
        self.assertEqual(cfg1.chunk_size, cfg2.chunk_size)


if __name__ == "__main__":
    unittest.main()
