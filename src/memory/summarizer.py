"""Configurable summarization with per-session thresholds and hierarchical compression.

Features:
- Per-session configurable threshold (stored in session context JSON)
- Hierarchical summarization: older chunks summarized more aggressively
- Keeps recent messages intact (configurable count)
- Supports force-summarize with custom settings
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from src.core.db.db_engine import get_engine
from src.core.db.models import Session, SessionMemory
from src.core.llm.factory import get_llm

logger = logging.getLogger(__name__)

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)

DEFAULT_THRESHOLD = 20
DEFAULT_KEEP_RECENT = 5
DEFAULT_CHUNK_SIZE = 10
MAX_CHUNK_SIZE = 50


@dataclass
class SummaryConfig:
    """Configuration for session summarization behavior."""

    threshold: int = DEFAULT_THRESHOLD
    keep_recent: int = DEFAULT_KEEP_RECENT
    chunk_size: int = DEFAULT_CHUNK_SIZE
    hierarchical: bool = True
    max_levels: int = 3

    @classmethod
    def from_json(cls, raw: str | None) -> SummaryConfig:
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
            summary_cfg = data.get("summary", {})
            return cls(
                threshold=summary_cfg.get("threshold", DEFAULT_THRESHOLD),
                keep_recent=summary_cfg.get("keep_recent", DEFAULT_KEEP_RECENT),
                chunk_size=summary_cfg.get("chunk_size", DEFAULT_CHUNK_SIZE),
                hierarchical=summary_cfg.get("hierarchical", True),
                max_levels=summary_cfg.get("max_levels", 3),
            )
        except (json.JSONDecodeError, TypeError):
            return cls()

    def to_context_dict(self) -> dict:
        return {
            "summary": {
                "threshold": self.threshold,
                "keep_recent": self.keep_recent,
                "chunk_size": self.chunk_size,
                "hierarchical": self.hierarchical,
                "max_levels": self.max_levels,
            }
        }


def get_summary_config(session_id: str) -> SummaryConfig:
    with SessionLocal() as db:
        row = db.execute(select(Session.context).where(Session.id == session_id)).scalar()
        return SummaryConfig.from_json(row)


def update_summary_config(session_id: str, cfg: SummaryConfig) -> None:
    with SessionLocal() as db:
        row = db.execute(select(Session.context).where(Session.id == session_id)).scalar()
        existing = {}
        if row:
            try:
                existing = json.loads(row)
            except (json.JSONDecodeError, TypeError):
                existing = {}
        existing.update(cfg.to_context_dict())
        db.execute(Session.__table__.update().where(Session.id == session_id).values(context=json.dumps(existing)))
        db.commit()


def _summarize_chunk(texts: list[str]) -> str:
    joined = "\n".join(texts)
    if not joined.strip():
        return ""
    llm = get_llm()
    prompt = (
        "Ringkas bagian percakapan berikut menjadi poin-poin inti (maks 3 kalimat). "
        "Fokus pada fakta, keputusan, dan konteks penting.\n\n"
        f"{joined}"
    )
    result = llm.invoke(prompt)
    content = getattr(result, "content", str(result))
    return str(content).strip()


def _summarize_final(texts: list[str]) -> str:
    joined = "\n".join(texts)
    if not joined.strip():
        return ""
    llm = get_llm()
    prompt = (
        "Buat ringkasan percakapan berikut dalam 3-5 kalimat. "
        "Sertakan: (1) topik utama, (2) keputusan/poin penting, (3) status tugas bila ada.\n\n"
        f"{joined}"
    )
    result = llm.invoke(prompt)
    content = getattr(result, "content", str(result))
    return str(content).strip()


def _hierarchical_summarize(messages: list[SessionMemory], cfg: SummaryConfig) -> str:
    summaries: list[str] = []

    for i in range(0, len(messages), cfg.chunk_size):
        chunk = messages[i : i + cfg.chunk_size]
        texts = [f"{m.role}: {m.content}" for m in chunk]
        summary = _summarize_chunk(texts)
        if summary:
            summaries.append(summary)

    if not summaries:
        return ""

    if len(summaries) == 1:
        return summaries[0]

    level = 1
    while len(summaries) > 1 and level < cfg.max_levels:
        next_level: list[str] = []
        for i in range(0, len(summaries), cfg.chunk_size):
            chunk = summaries[i : i + cfg.chunk_size]
            if len(chunk) == 1:
                next_level.append(chunk[0])
            else:
                merged = "\n".join(chunk)
                llm = get_llm()
                prompt = (
                    f"Gabungkan {len(chunk)} ringkasan berikut menjadi satu ringkasan "
                    "yang koheren (maks 4 kalimat):\n\n"
                    f"{merged}"
                )
                result = llm.invoke(prompt)
                content = getattr(result, "content", str(result))
                next_level.append(str(content).strip())
        summaries = next_level
        level += 1

    return summaries[0] if summaries else ""


def summarize_session(session_id: str, config: SummaryConfig | None = None) -> str:
    cfg = config or get_summary_config(session_id)

    with SessionLocal() as session:
        stmt = select(SessionMemory).where(SessionMemory.session_id == session_id).order_by(SessionMemory.timestamp)
        results = session.execute(stmt).scalars().all()

        total = len(results)
        if total < cfg.threshold:
            logger.debug(
                "Session %s: %d messages < threshold %d, skipping",
                session_id,
                total,
                cfg.threshold,
            )
            return ""

        keep_count = cfg.keep_recent
        messages_to_summarize = results[: total - keep_count]
        messages_to_keep = results[total - keep_count :]

        if not messages_to_summarize:
            return ""

        summary = _hierarchical_summarize(messages_to_summarize, cfg)

        if not summary:
            return ""

        session.execute(delete(SessionMemory).where(SessionMemory.session_id == session_id))

        try:
            summary_msg = SessionMemory(
                session_id=session_id,
                owner_user_id="default",
                role="system",
                content=f"RINGKASAN PERCAKAPAN SEBELUMNYA ({len(messages_to_summarize)} pesan diringkas): {summary}",
            )
        except TypeError:
            summary_msg = SessionMemory(
                session_id=session_id,
                role="system",
                content=f"RINGKASAN PERCAKAPAN SEBELUMNYA ({len(messages_to_summarize)} pesan diringkas): {summary}",
            )
        session.add(summary_msg)

        for msg in messages_to_keep:
            try:
                session.add(
                    SessionMemory(session_id=session_id, owner_user_id="default", role=msg.role, content=msg.content)
                )
            except TypeError:
                session.add(SessionMemory(session_id=session_id, role=msg.role, content=msg.content))
        session.commit()

        logger.info(
            "Session %s: summarized %d messages, kept %d recent",
            session_id,
            len(messages_to_summarize),
            len(messages_to_keep),
        )
        return summary


def force_summarize(session_id: str, threshold: int | None = None) -> str:
    cfg = get_summary_config(session_id)
    if threshold is not None:
        cfg.threshold = threshold
    return summarize_session(session_id, config=cfg)
