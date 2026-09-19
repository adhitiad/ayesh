from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from src.core.db_engine import get_engine
from src.core.models import Monologue


def _session_local():
    """Session factory lazy — import modul aman tanpa DATABASE_URL."""
    return sessionmaker(bind=get_engine())


def add_monologue(user_id: str, agent_type: str, role: str, content: str):
    """Tambahkan monologue untuk user dan agent tertentu."""
    SessionLocal = _session_local()
    with SessionLocal() as session:
        monologue = Monologue(
            user_id=user_id, agent_type=agent_type, role=role, content=content
        )
        session.add(monologue)
        session.commit()


def get_latest_monologue(user_id: str, agent_type: str):
    """Ambil monologue terbaru untuk user dan agent tertentu."""
    SessionLocal = _session_local()
    with SessionLocal() as session:
        result = session.execute(
            select(Monologue)
            .where(Monologue.user_id == user_id, Monologue.agent_type == agent_type)
            .order_by(Monologue.timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()
        return result


def get_role_for_agent(agent_type: str):
    """Dapatkan role yang sesuai untuk agent type."""
    role_map = {
        "coder_agent": "developer",
        "admin_agent": "executive",
        "casual_agent": "assistant",
        "coder": "developer",
        "admin": "executive",
        "casual": "assistant",
    }
    return role_map.get(agent_type, "assistant")
