import logging
import re
from src.core.async_log_handler import AsyncPostgresLogHandler

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

    COLORS = {
        "WARNING": "\033[93m",  # kuning cerah
        "INFO": "\033[32m",  # hijau tua
        "ERROR": "\033[91m",  # merah
        "CRITICAL": "\033[95m",
    }
    RESET = "\033[0m"

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
