"""Long-term cross-session memory tools: ingat_fakta, lihat_fakta, cari_fakta."""

import logging
from datetime import UTC, datetime

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.core.db.db_engine import get_engine
from src.core.db.models import UserMemory
from src.plugins.tool_error import tool_error_from_exception

logger = logging.getLogger(__name__)

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)


def _get_owner_user_id() -> str:
    """Get current owner user ID for memory scoping."""
    try:
        from src.core.auth.auth import get_current_user_id

        uid = get_current_user_id()
        if uid and uid != "default":
            return uid
    except Exception as e:
        logger.debug("_get_owner_user_id error: %s", e)
    return "anonymous"


@tool
def ingat_fakta(
    key: str,
    value: str,
    fact_type: str = "fact",
    confidence: float = 1.0,
) -> str:
    """Simpan fakta/preferensi/keputusan/goal user lintas session (long-term memory).

    Pakai saat user menyatakan sesuatu yang layak diingat jangka panjang.
    Berbeda dari preferensi (key-value sederhana), ini mendukung:
    - fact_type: fact | preference | decision | goal
    - confidence: 0.0 - 1.0 (seberapa yakin fakta ini akurat)
    - Pencarian semantik di masa depan

    JANGAN untuk info sesaat, rahasia (password, token, OTP), atau PII sensitif.

    Args:
        key: Kunci singkat lowercase, deskriptif. Contoh: nama_lengkap, framework_favorit, keputusan_db.
        value: Nilai fakta. Contoh: Budi Santoso, FastAPI, Migrasi ke PostgreSQL.
        fact_type: Kategori fakta. Default fact. Pilihan: fact, preference, decision, goal.
        confidence: Tingkat kepercayaan 0.0-1.0. Default 1.0.
    """
    try:
        key = key.strip().lower().replace(" ", "_")[:100]
        value = value.strip()[:2000]
        fact_type = fact_type.strip().lower()
        if not key or not value:
            return "Error: key dan value tidak boleh kosong."
        if fact_type not in ("fact", "preference", "decision", "goal"):
            return "Error: fact_type harus salah satu: fact, preference, decision, goal."
        confidence = max(0.0, min(1.0, float(confidence)))

        owner_id = _get_owner_user_id()
        with SessionLocal() as session:
            existing = session.execute(
                select(UserMemory).where(UserMemory.owner_user_id == owner_id, UserMemory.key == key)
            ).scalar_one_or_none()

            if existing:
                existing.value = value
                existing.fact_type = fact_type
                existing.confidence = confidence
                existing.updated_at = datetime.now(UTC)
            else:
                session.add(
                    UserMemory(
                        owner_user_id=owner_id,
                        user_id=owner_id,
                        fact_type=fact_type,
                        key=key,
                        value=value,
                        confidence=confidence,
                    )
                )
            session.commit()
        return f"Fakta tersimpan: [{fact_type}] {key} = {value} (confidence: {confidence})"
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def lihat_fakta(fact_type: str | None = None) -> str:
    """Lihat semua fakta user yang tersimpan lintas session.

    Args:
        fact_type: Filter berdasarkan tipe. Kosong = semua. Pilihan: fact, preference, decision, goal.
    """
    try:
        owner_id = _get_owner_user_id()
        with SessionLocal() as session:
            stmt = select(UserMemory).where(UserMemory.owner_user_id == owner_id)
            if fact_type:
                stmt = stmt.where(UserMemory.fact_type == fact_type.strip().lower())
            stmt = stmt.order_by(UserMemory.fact_type, UserMemory.key)
            rows = session.execute(stmt).scalars().all()

        if not rows:
            return "Belum ada fakta tersimpan." + (f" (filter: {fact_type})" if fact_type else "")

        lines = ["Fakta user (long-term memory):"]
        current_type = None
        for row in rows:
            if row.fact_type != current_type:
                current_type = row.fact_type
                lines.append(f"\n--- {current_type.upper()} ---")
            conf = f" ({row.confidence:.0%})" if row.confidence < 1.0 else ""
            lines.append(f"- {row.key}: {row.value}{conf}")
        return "\n".join(lines)
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def cari_fakta(query: str, limit: int = 10) -> str:
    """Cari fakta user berdasarkan query teks (substring match di key dan value).

    Args:
        query: Kata kunci pencarian.
        limit: Maksimal hasil (default 10).
    """
    try:
        owner_id = _get_owner_user_id()
        query_lower = query.strip().lower()
        if not query_lower:
            return "Error: query tidak boleh kosong."
        limit = max(1, min(50, int(limit)))

        with SessionLocal() as session:
            stmt = (
                select(UserMemory)
                .where(
                    UserMemory.owner_user_id == owner_id,
                    (UserMemory.key.ilike(f"%{query_lower}%")) | (UserMemory.value.ilike(f"%{query_lower}%")),
                )
                .order_by(UserMemory.confidence.desc(), UserMemory.updated_at.desc())
                .limit(limit)
            )
            rows = session.execute(stmt).scalars().all()

        if not rows:
            return f"Tidak ditemukan fakta untuk query: {query}"

        lines = [f"Hasil pencarian {query}:"]
        for row in rows:
            conf = f" ({row.confidence:.0%})" if row.confidence < 1.0 else ""
            lines.append(f"- [{row.fact_type}] {row.key}: {row.value}{conf}")
        return "\n".join(lines)
    except Exception as e:
        return tool_error_from_exception(e)
