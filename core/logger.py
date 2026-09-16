import logging
from core.async_log_handler import AsyncPostgresLogHandler

class ColoredFormatter(logging.Formatter):
    """Formatter dengan warna ANSI untuk level logging."""
    COLORS = {
        "WARNING": "\033[93m",  # kuning cerah
        "INFO": "\033[32m",     # hijau tua
        "ERROR": "\033[91m",    # merah
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

    # Hindari duplikasi handler
    if logger.handlers:
        return logger

    # Buat handler untuk menampilkan log ke console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)

    # Buat formatter dengan warna
    formatter = ColoredFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)

    # Buat handler async untuk menyimpan log ke PostgreSQL
    db_handler = AsyncPostgresLogHandler()
    db_handler.setLevel(level)
    db_handler.setFormatter(formatter)

    # Tambahkan handler ke logger
    logger.addHandler(console_handler)
    logger.addHandler(db_handler)

    return logger
