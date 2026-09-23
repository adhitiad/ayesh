import logging
from queue import Queue
from threading import Thread

from sqlalchemy.orm import sessionmaker

from src.core.db.db_engine import get_engine
from src.core.db.models import LogEntry

_engine = get_engine()
_SessionLocal = sessionmaker(bind=_engine)


class AsyncPostgresLogHandler(logging.Handler):
    """Async logging handler using a single global worker thread."""

    _queue: Queue = Queue()
    _worker_started = False

    def __init__(self):
        super().__init__()
        if not AsyncPostgresLogHandler._worker_started:
            t = Thread(target=self._worker, daemon=True)
            t.start()
            AsyncPostgresLogHandler._worker_started = True

    def emit(self, record: logging.LogRecord) -> None:
        import contextlib

        with contextlib.suppress(Exception):  # Queue full: drop record (non-critical)
            self._queue.put_nowait(record)

    def _worker(self):
        while True:
            record = self._queue.get()
            if record is None:
                break
            try:
                with _SessionLocal() as session:
                    log_entry = LogEntry(
                        logger_name=record.name,
                        level=record.levelname,
                        message=self.format(record),
                    )
                    session.add(log_entry)
                    session.commit()
            except Exception:  # noqa: S110 — DB log write failed: drop record (non-critical)  # nosec B110
                pass
            finally:
                self._queue.task_done()
