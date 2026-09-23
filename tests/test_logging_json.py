"""Test structured logging JSON + request ID tracing (unittest, cepat, tanpa infra)."""

import json
import logging
import unittest

from src.core.observability.logger import (
    JsonFormatter,
    get_request_id,
    get_session_id,
    redact_secrets,
    request_log_context,
    set_request_id,
    set_session_id,
)
from src.core.system.error_handling import generate_request_id, log_internal_error


def _make_record(msg: str = "halo %s", args: tuple = ("dunia",), **attrs) -> logging.LogRecord:
    record = logging.LogRecord(
        name="tests", level=logging.INFO, pathname=__file__, lineno=1, msg=msg, args=args, exc_info=None
    )
    for key, value in attrs.items():
        setattr(record, key, value)
    return record


class TestJsonFormatter(unittest.TestCase):
    def test_emits_valid_json_with_core_fields(self):
        line = JsonFormatter().format(_make_record())
        payload = json.loads(line)
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "tests")
        self.assertEqual(payload["message"], "halo dunia")
        self.assertIn("ts", payload)

    def test_request_id_from_record_attr(self):
        line = JsonFormatter().format(_make_record(request_id="req-abc"))
        payload = json.loads(line)
        self.assertEqual(payload["request_id"], "req-abc")

    def test_request_id_from_contextvar_when_record_lacks_attr(self):
        set_request_id("req-ctx")
        try:
            line = JsonFormatter().format(_make_record())
        finally:
            set_request_id(None)
        payload = json.loads(line)
        self.assertEqual(payload["request_id"], "req-ctx")

    def test_explicit_record_attr_wins_over_contextvar(self):
        set_request_id("req-ctx")
        try:
            line = JsonFormatter().format(_make_record(request_id="req-explicit"))
        finally:
            set_request_id(None)
        payload = json.loads(line)
        self.assertEqual(payload["request_id"], "req-explicit")

    def test_session_id_from_contextvar(self):
        set_session_id("ses-1")
        try:
            line = JsonFormatter().format(_make_record())
        finally:
            set_session_id(None)
        payload = json.loads(line)
        self.assertEqual(payload["session_id"], "ses-1")

    def test_redacts_secrets_in_output(self):
        msg = "key=sk-ABCDEFGHIJKLMNOPQRSTUVWXY123456 dan tvly-abc1234567"
        line = JsonFormatter().format(_make_record(msg=msg, args=()))
        self.assertNotIn("sk-ABCDEFGHIJKLMNOPQRSTUVWXY123456", line)
        self.assertNotIn("tvly-abc1234567", line)
        payload = json.loads(line)
        self.assertEqual(payload["message"], redact_secrets(msg))

    def test_extra_keys_included(self):
        rec = _make_record()
        rec.context = "chat"
        rec.elapsed_ms = 12
        payload = json.loads(JsonFormatter().format(rec))
        self.assertEqual(payload["context"], "chat")
        self.assertEqual(payload["elapsed_ms"], 12)


class TestRequestIdContext(unittest.TestCase):
    def test_get_set_roundtrip(self):
        set_request_id("req-1")
        try:
            self.assertEqual(get_request_id(), "req-1")
        finally:
            set_request_id(None)
        self.assertIsNone(get_request_id())

    def test_request_log_context_seeds_and_restores(self):
        set_request_id("outer")
        set_session_id("outer-ses")
        try:
            with request_log_context(request_id="inner", session_id="inner-ses"):
                self.assertEqual(get_request_id(), "inner")
                self.assertEqual(get_session_id(), "inner-ses")
            self.assertEqual(get_request_id(), "outer")
            self.assertEqual(get_session_id(), "outer-ses")
        finally:
            set_request_id(None)
            set_session_id(None)

    def test_generate_request_id_reuses_contextvar(self):
        set_request_id("req-pin")
        try:
            self.assertEqual(generate_request_id(), "req-pin")
        finally:
            set_request_id(None)
        generated = generate_request_id()
        self.assertRegex(generated, r"^[0-9a-f]{12}$")
        self.assertNotEqual(generated, "req-pin")


class TestLogInternalErrorTracing(unittest.TestCase):
    def test_seeds_contextvar_and_record_attr(self):
        captured = []

        class _Capture(logging.Handler):
            def emit(self, record):
                captured.append(record)

        err_logger = logging.getLogger("errors")
        handler = _Capture(level=logging.ERROR)
        err_logger.addHandler(handler)
        try:
            log_internal_error("req-trace", ValueError("gagal proses"), context="test")
        finally:
            err_logger.removeHandler(handler)
        self.assertEqual(len(captured), 1)
        rec = captured[0]
        self.assertEqual(rec.request_id, "req-trace")
        self.assertEqual(rec.context, "test")
        message = rec.getMessage()
        self.assertIn("[req-trace]", message)
        self.assertIn("gagal proses", message)

    def test_message_still_redacted(self):
        captured = []

        class _Capture(logging.Handler):
            def emit(self, record):
                captured.append(record)

        err_logger = logging.getLogger("errors")
        handler = _Capture(level=logging.ERROR)
        err_logger.addHandler(handler)
        try:
            log_internal_error("req-red", ValueError("token tvly-abc1234567 bocor"), context="test")
        finally:
            err_logger.removeHandler(handler)
        self.assertNotIn("tvly-abc1234567", captured[0].getMessage())


if __name__ == "__main__":
    unittest.main()
