"""pytest configuration & fixtures untuk factory_boy (#21)."""

import pytest
import pytest_factoryboy
from sqlalchemy.orm import sessionmaker

from src.core.db.db_engine import get_engine
from tests import factories as factory_module


@pytest.fixture(scope="session")
def db_engine():
    """Database engine untuk test (session-scoped)."""
    return get_engine()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """SQLAlchemy session per test function, rollback otomatis."""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def _set_factory_session(db_session):
    """Attach SQLAlchemy session ke semua factory untuk persist per-test (opt-in)."""
    for attr_name in dir(factory_module):
        if attr_name.endswith("Factory"):
            factory_cls = getattr(factory_module, attr_name)
            if hasattr(factory_cls, "_meta"):
                factory_cls._meta.sqlalchemy_session = db_session
    yield
    for attr_name in dir(factory_module):
        if attr_name.endswith("Factory"):
            factory_cls = getattr(factory_module, attr_name)
            if hasattr(factory_cls, "_meta"):
                factory_cls._meta.sqlalchemy_session = None


# Register setiap factory → fixture `<nama>_factory` + `<nama>` (model instance)
pytest_factoryboy.register(factory_module.SessionFactory)
pytest_factoryboy.register(factory_module.RoutingKeywordFactory)
pytest_factoryboy.register(factory_module.SessionMemoryFactory)
pytest_factoryboy.register(factory_module.LogEntryFactory)
pytest_factoryboy.register(factory_module.FeedbackFactory)
pytest_factoryboy.register(factory_module.ToolFailureFactory)
pytest_factoryboy.register(factory_module.RoutingLearningFactory)
pytest_factoryboy.register(factory_module.MonologueFactory)
pytest_factoryboy.register(factory_module.UserFactory)
pytest_factoryboy.register(factory_module.PreferensiFactory)
pytest_factoryboy.register(factory_module.ProyekFactory)
pytest_factoryboy.register(factory_module.PlanFactory)
pytest_factoryboy.register(factory_module.PlanStepFactory)
pytest_factoryboy.register(factory_module.PendingApprovalFactory)
pytest_factoryboy.register(factory_module.AuditLogFactory)
pytest_factoryboy.register(factory_module.ScheduledJobFactory)
pytest_factoryboy.register(factory_module.BackgroundTaskFactory)
pytest_factoryboy.register(factory_module.RequestStatFactory)
