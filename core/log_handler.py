from logging import Handler, LogRecord
from sqlalchemy.orm import sessionmaker
from core.db_engine import get_engine
from core.models import LogEntry

_engine = get_engine()
_SessionLocal = sessionmaker(bind=_engine)

class PostgresLogHandler(Handler):
    """Synchronous logging handler that saves logs to PostgreSQL."""

    def emit(self, record: LogRecord) -> None:
        try:
            with _SessionLocal() as session:
                log_entry = LogEntry(
                    logger_name=record.name,
                    level=record.levelname,
                    message=self.format(record),
                )
                session.add(log_entry)
                session.commit()
        except Exception:
            pass
