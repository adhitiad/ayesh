"""Session helpers: get/create, update, auto-nama via LLM (pindahan dari main.py)."""

import json
import re
from datetime import datetime

from core.db_engine import get_engine
from core.models import Session
from sqlalchemy.orm import sessionmaker

from core.logger import setup_logger

logger = setup_logger("sessions")


def _session_local():
    return sessionmaker(bind=get_engine())


def get_or_create_session(session_id: str) -> dict:
    """Ambil session dari DB, atau buat baru jika belum ada."""
    with _session_local()() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
        if sess:
            return {
                "id": sess.id,
                "nama": sess.nama,
                "context": sess.context,
                "agent_type": sess.agent_type,
                "created_at": str(sess.created_at),
            }
        new_sess = Session(id=session_id, nama=None, context=None, agent_type=None)
        db.add(new_sess)
        db.commit()
        return {
            "id": session_id,
            "nama": None,
            "context": None,
            "agent_type": None,
        }


def update_session(session_id: str, nama: str = None, context: str = None, agent_type: str = None):
    """Update nama/context/agent_type session (hanya field non-None)."""
    with _session_local()() as db:
        sess = db.query(Session).filter(Session.id == session_id).first()
        if sess:
            if nama is not None:
                sess.nama = nama
            if context is not None:
                sess.context = context
            if agent_type is not None:
                sess.agent_type = agent_type
            sess.updated_at = datetime.utcnow()
            db.commit()


def generate_session_name_context(user_input: str, answer: str) -> tuple[str, str]:
    """Gunakan LLM untuk generate nama dan context session dari percakapan."""
    try:
        from agents.llm_config import get_llm
        llm = get_llm()
        prompt = f"""Berdasarkan percakapan berikut, buat:
1. Nama session (max 50 kata, singkat, deskriptif)
2. Context session (1-2 kalimat, apa yang dibahas)

User: {user_input[:500]}
Assistant: {answer[:500]}

Jawab HANYA dengan JSON:
{{"nama": "nama session", "context": "context percakapan"}}"""

        response = llm.invoke(prompt)
        from core.text import extract_text
        content = extract_text(response.content if hasattr(response, "content") else str(response))

        # Kupas markdown fence bila ada (```json ... ```)
        content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip())
        try:
            data = json.loads(content)
            return data.get("nama", ""), data.get("context", "")
        except (json.JSONDecodeError, AttributeError):
            pass
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return data.get("nama", ""), data.get("context", "")
            except json.JSONDecodeError:
                pass
        return "", ""
    except Exception as e:
        logger.error(f"Gagal generate session name: {e}")
        return "", ""
