from logging import Handler, LogRecord
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from core.models import LogEntry

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Setup SQLAlchemy engine for logging
# We use a separate engine to avoid session conflicts with main app logic
log_engine = create_engine(DATABASE_URL)
LogSession = sessionmaker(bind=log_engine)

class PostgresLogHandler(Handler):
    """Custom logging handler that saves logs to PostgreSQL."""
    
    def emit(self, record: LogRecord) -> None:
        try:
            # Create a session and save the log entry
            with LogSession() as session:
                log_entry = LogEntry(
                    logger_name=record.name,
                    level=record.levelname,
                    message=self.format(record)
                )
                session.add(log_entry)
                session.commit()
        except Exception:
            # Fail silently to avoid crashing the application due to logging errors
            pass
