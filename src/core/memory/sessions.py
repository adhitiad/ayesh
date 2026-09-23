"""Session helpers: get/create, update, auto-nama via LLM (pindahan dari main.py)."""

import json
import re
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from src.core.db.db_engine import get_engine
from src.core.db.models import Base, Session
from src.core.observability.logger import setup_logger

logger = setup_logger("sessions")


def _ensure_table(cur=None):
    """Ensure sessions table exists. Accepts cursor (no-op) for backward compat."""
    Base.metadata.create_all(get_engine(), tables=[Session.__table__])


def _session_local():
    return sessionmaker(bind=get_engine())


def get_or_create_session(session_id: str, user_id: str = "default", owner_user_id: str | None = None) -> dict:
    """Ambil session dari DB, atau buat baru jika belum ada."""
    if not owner_user_id:
        owner_user_id = user_id
    _ensure_table()
    with _session_local()() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
        if sess:
            return {
                "id": sess.id,
                "owner_user_id": sess.owner_user_id,
                "user_id": sess.user_id,
                "nama": sess.nama,
                "context": sess.context,
                "agent_type": sess.agent_type,
                "created_at": str(sess.created_at),
            }
        new_sess = Session(
            id=session_id,
            owner_user_id=owner_user_id,
            user_id=user_id,
            nama=None,
            context=None,
            agent_type=None,
        )
        db.add(new_sess)
        db.commit()
        return {
            "id": session_id,
            "owner_user_id": owner_user_id,
            "user_id": user_id,
            "nama": None,
            "context": None,
            "agent_type": None,
        }


def update_session(
    session_id: str,
    nama: str | None = None,
    context: str | None = None,
    agent_type: str | None = None,
    owner_user_id: str | None = None,
):
    """Update nama/context/agent_type session (hanya field non-None)."""
    _ensure_table()
    with _session_local()() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
        if sess:
            if owner_user_id is not None:
                sess.owner_user_id = owner_user_id
            if nama is not None:
                sess.nama = nama
            if context is not None:
                sess.context = context
            if agent_type is not None:
                sess.agent_type = agent_type
            sess.updated_at = datetime.now(UTC)
            db.commit()


def generate_session_name_context(user_input: str, answer: str) -> tuple[str, str]:
    """Gunakan LLM untuk generate nama dan context session dari percakapan."""
    try:
        from src.core.llm.factory import get_llm

        llm = get_llm()
        prompt = f"""Berdasarkan percakapan berikut, buat:
1. Nama session (max 50 kata, singkat, deskriptif)
2. Context session (1-2 kalimat, apa yang dibahas)

User: {user_input[:500]}
Assistant: {answer[:500]}

Output JSON: {{"nama": "...", "context": "..."}}"""
        resp = llm.invoke(prompt)
        text = resp.content if hasattr(resp, "content") else str(resp)
        # Extract JSON from response
        match = re.search(r"\{[^}]+\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get("nama", ""), data.get("context", "")
    except Exception as e:
        logger.debug("generate_session_name_context error: %s", e)
    return "", ""
