"""Logging: redaksi secret, JSON structured logging opsional, propagasi request ID.

Console berwarna (ColoredFormatter) + PostgreSQL async (AsyncPostgresLogHandler)
tetap seperti sebelumnya. Di atasnya ditambah JSON structured logging ke file
berotasi (logs/ayesh.jsonl default; nonaktif: LOG_JSON_ENABLED=0; jalur custom:
LOG_JSON_FILE=<path>). Request ID + session ID disebarkan lewat ContextVar sehingga
field request_id muncul di setiap baris JSON tanpa mengubah signature pemanggil.
"""

import json
import logging
import logging.handlers
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import ClassVar

from src.core.db.async_log_handler import AsyncPostgresLogHandler

_SECRET_PATTERNS = [
    # API keys
    r"tavilyApiKey=[^&\s'\"]+",
    r"tvly-[A-Za-z0-9_\-]+",
    r"AIza[A-Za-z0-9_\-]{20,}",
    r"gsk_[A-Za-z0-9]+",
    r"nvapi-[\w.\-]+",
    r"fr_[a-f0-9]{16,}",
    # GitHub tokens
    r"ghp_[A-Za-z0-9]+",
    r"github_pat_[A-Za-z0-9_]+",
    r"gho_[A-Za-z0-9]+",
    r"ghs_[A-Za-z0-9]+",
    r"ghr_[A-Za-z0-9]+",
    # P3.5 — Expanded patterns
    r"Bearer\s+[A-Za-z0-9\-_\.]+",
    r"Authorization:\s*Bearer\s+\S+",
    r"X-API-Key:\s*\S+",
    r"sk-[A-Za-z0-9\-]{20,}",  # OpenAI generic
    r"sk-ant-[A-Za-z0-9\-]+",  # Anthropic
    r"AKIA[A-Z0-9]{16}",  # AWS access key
    r"(?:password|passwd|pwd)\s*[:=]\s*\S+",  # password assignments
    r"(?:telegram|tg)_bot_token\s*[:=]\s*\S+",
    r"postgres(?:ql)?://[^@\s]+@[^/\s]+",  # database URL with password
    r"redis://[^@\s]+@[^/\s]+",  # Redis URL with password
    r"mongodb(?:\+srv)?://[^@\s]+@[^/\s]+",  # MongoDB URL with password
]
_SECRET_RES = [re.compile(p, re.IGNORECASE) for p in _SECRET_PATTERNS]


def redact_secrets(text: str) -> str:
    """Ganti API key/token dengan ***REDACTED***. Pure, testable."""
    for rx in _SECRET_RES:
        text = rx.sub("***REDACTED***", text)
    return text


class _RedactSecrets(logging.Filter):
    """Redaksi sebelum ke console maupun PostgreSQL."""

    def filter(self, record):
        try:
            msg = record.getMessage()
            red = redact_secrets(msg)
            if red != msg:
                record.msg = red
                record.args = ()
        except Exception as _e:
            import sys

            print(f"[redact_secrets] filter error: {_e}", file=sys.stderr)
        return True


class ColoredFormatter(logging.Formatter):
    """Formatter dengan warna ANSI untuk level logging."""

    COLORS: ClassVar[dict[str, str]] = {
        "WARNING": "\033[93m",  # kuning cerah
        "INFO": "\033[32m",  # hijau tua
        "ERROR": "\033[91m",  # merah
        "CRITICAL": "\033[95m",
    }
    RESET: ClassVar[str] = "\033[0m"

    def format(self, record):
        levelname = record.levelname
        color = self.COLORS.get(levelname, "")
        # Warnai levelname, name, dan message sesuai level
        original_levelname = record.levelname
        record.levelname = f"{color}{levelname}{self.RESET}"
        # Warnai nama logger juga
        original_name = record.name
        record.name = f"{color}{record.name}{self.RESET}"
        formatted = super().format(record)
        record.levelname = original_levelname
        record.name = original_name
        # Warnai seluruh baris untuk kontras lebih jelas
        if color:
            formatted = f"{color}{formatted}{self.RESET}"
        return formatted


# ── Propagasi request/session ID via ContextVar ─────────────────────
_request_id: ContextVar[str | None] = ContextVar("log_request_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("log_session_id", default=None)


def get_request_id() -> str | None:
    """Request ID ContextVar aktif (bila ada)."""
    return _request_id.get()


def set_request_id(request_id: str | None) -> None:
    """Seed request ID untuk semua log di konteks/thread saat ini."""
    _request_id.set(request_id or None)


def get_session_id() -> str | None:
    """Session ID ContextVar aktif (bila ada)."""
    return _session_id.get()


def set_session_id(session_id: str | None) -> None:
    """Seed session ID untuk semua log di konteks/thread saat ini."""
    _session_id.set(session_id or None)


@contextmanager
def request_log_context(request_id: str | None = None, session_id: str | None = None) -> Iterator[None]:
    """Seed ContextVar request/session ID; dipulihkan setelah keluar (kill nested)."""
    prev_rid, prev_sid = _request_id.get(), _session_id.get()
    if request_id:
        _request_id.set(request_id)
    if session_id:
        _session_id.set(session_id)
    try:
        yield
    finally:
        _request_id.set(prev_rid)
        _session_id.set(prev_sid)


# ── JSON structured logging ─────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    """Formatter satu-baris JSON.

    request_id/session_id diambil dari record.extra (bila ada) atau ContextVar
    (propagasi global tanpa mengubah pemanggil). Seluruh baris di-redaksi ulang.
    """

    EXTRA_KEYS = (
        "request_id",
        "session_id",
        "context",
        "agent_type",
        "user_id",
        "scope",
        "route",
        "elapsed_ms",
    )

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z")
        payload: dict = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = getattr(record, "request_id", None) or _request_id.get()
        if rid:
            payload["request_id"] = rid
        sid = getattr(record, "session_id", None) or _session_id.get()
        if sid:
            payload["session_id"] = sid
        for key in self.EXTRA_KEYS:
            if key in payload:
                continue
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        try:
            line = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            fallback = {
                "ts": ts,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            line = json.dumps(fallback, ensure_ascii=False)
        return redact_secrets(line)


_JSON_HANDLER_ATTACHED = False
_DEFAULT_LOG_FILE = os.getenv("LOG_JSON_FILE", "").strip() or "logs/ayesh.jsonl"


def _attach_json_file_handler() -> None:
    """Satu file handler JSON di root logger (singleton). Nonaktif: LOG_JSON_ENABLED=0."""
    global _JSON_HANDLER_ATTACHED
    if _JSON_HANDLER_ATTACHED:
        return
    _JSON_HANDLER_ATTACHED = True
    if os.getenv("LOG_JSON_ENABLED", "1").strip() == "0":
        return
    try:
        log_path = os.path.abspath(_DEFAULT_LOG_FILE)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(JsonFormatter())
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)
    except OSError as _e:
        import sys

        print(f"[logger] JSON file handler gagal dibuat ({_DEFAULT_LOG_FILE}): {_e}", file=sys.stderr)


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Buat logger dengan nama dan level tertentu.

    Args:
        name (str): Nama logger.
        level (int, optional): Level logging. Default: logging.INFO.

    Returns:
        logging.Logger: Logger yang sudah dikonfigurasi.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not any(isinstance(f, _RedactSecrets) for f in logger.filters):
        logger.addFilter(_RedactSecrets())

    # JSON structured logging (singleton di root; langsung jalan bila diaktifkan)
    _attach_json_file_handler()

    # Hindari duplikasi handler
    if logger.handlers:
        return logger

    # Buat handler untuk menampilkan log ke console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)

    # Buat formatter dengan warna
    formatter = ColoredFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)

    # Buat handler async untuk menyimpan log ke PostgreSQL
    db_handler = AsyncPostgresLogHandler()
    db_handler.setLevel(level)
    db_handler.setFormatter(formatter)

    # Tambahkan handler ke logger
    logger.addHandler(console_handler)
    logger.addHandler(db_handler)

    return logger
