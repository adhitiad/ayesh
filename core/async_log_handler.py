import logging
from logging import LogRecord
from queue import Queue
from threading import Thread
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
from core.models import LogEntry

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

log_engine = create_engine(DATABASE_URL)
LogSession = sessionmaker(bind=log_engine)

class AsyncPostgresLogHandler(logging.Handler):
    """Async logging handler using a background thread and queue."""
    
    def __init__(self):
        super().__init__()
        self.queue = Queue()
        self.worker = Thread(target=self._worker, daemon=True)
        self.worker.start()

    def emit(self, record: LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except Exception:
            pass

    def _worker(self):
        while True:
            record = self.queue.get()
            if record is None:
                break
            try:
                with LogSession() as session:
                    log_entry = LogEntry(
                        logger_name=record.name,
                        level=record.levelname,
                        message=self.format(record)
                    )
                    session.add(log_entry)
                    session.commit()
            except Exception:
                pass
            finally:
                self.queue.task_done()
