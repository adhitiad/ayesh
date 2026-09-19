"""Session helpers: get/create, update, auto-nama via LLM (pindahan dari main.py)."""

import json
import re
from datetime import datetime

from sqlalchemy.orm import sessionmaker

from src.core.db.db_engine import get_engine
from src.core.db.models import Session
from src.core.observability.logger import setup_logger

logger = setup_logger("sessions")


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            user_id TEXT NOT NULL DEFAULT 'default',
            nama TEXT,
            context TEXT,
            agent_type TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    # Migration: add owner_user_id column if missing
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'sessions' AND column_name = 'owner_user_id'
            ) THEN
                ALTER TABLE sessions ADD COLUMN owner_user_id TEXT NOT NULL DEFAULT 'default';
            END IF;
        END $$;
    """)
    # Migration: add user_id column if missing
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'sessions' AND column_name = 'user_id'
            ) THEN
                ALTER TABLE sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';
            END IF;
        END $$;
    """)


def _session_local():
    return sessionmaker(bind=get_engine())


def get_or_create_session(
    session_id: str, user_id: str = "default", owner_user_id: str | None = None
) -> dict:
    """Ambil session dari DB, atau buat baru jika belum ada."""
    if not owner_user_id:
        owner_user_id = user_id
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.close()
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
    conn = _conn()
    cur = conn.cursor()
    _ensure_table(cur)
    conn.close()
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
            sess.updated_at = datetime.now(datetime.timezone.utc)
            db.commit()


def generate_session_name_context(user_input: str, answer: str) -> tuple[str, str]:
    """Gunakan LLM untuk generate nama dan context session dari percakapan."""
    try:
        from src.agents.llm_config import get_llm

        llm = get_llm()
        prompt = f"""Berdasarkan percakapan berikut, buat:
1. Nama session (max 50 kata, singkat, deskriptif)
2. Context session (1-2 kalimat, apa yang dibahas)

User: {user_input[:500]}
Assistant: {answer[:500]}

Jawab HANYA dengan JSON:
{{"nama": "nama session", "context": "context percakapan"}}"""

        response = llm.invoke(prompt)
        from src.core.llm.text import extract_text

        content = extract_text(
            response.content if hasattr(response, "content") else str(response)
        )

        # Kupas markdown fence bila ada (```json ... ```)
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        try:
            data = json.loads(content)
            return data.get("nama", ""), data.get("context", "")
        except (json.JSONDecodeError, AttributeError):
            pass
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
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


def _conn():
    from src.core.db.db import connect

    return connect()
