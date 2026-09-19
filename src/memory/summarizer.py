from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from src.agents.llm_config import get_llm
from src.core.db.db_engine import get_engine
from src.core.db.models import SessionMemory

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)

SUMMARY_THRESHOLD = 20  # Jumlah pesan sebelum diringkas

def summarize_session(session_id: str):
    with SessionLocal() as session:
        stmt = select(SessionMemory).where(SessionMemory.session_id == session_id).order_by(SessionMemory.timestamp)
        results = session.execute(stmt).scalars().all()

        if len(results) < SUMMARY_THRESHOLD:
            return

        # Buat teks gabungan dari pesan
        history_text = "\n".join([f"{r.role}: {r.content}" for r in results])

        # Ringkas menggunakan LLM
        llm = get_llm()
        prompt = f"Ringkaskan percakapan berikut menjadi 3-5 kalimat inti:\n\n{history_text}"
        summary = llm.invoke(prompt).content

        # Hapus history lama
        session.execute(delete(SessionMemory).where(SessionMemory.session_id == session_id))
        session.commit()

        # Simpan ringkasan sebagai pesan sistem
        new_mem = SessionMemory(
            session_id=session_id,
            role="system",
            content=f"RINGKASAN PERCAKAPAN SEBELUMNYA: {summary}"
        )
        session.add(new_mem)
        session.commit()
