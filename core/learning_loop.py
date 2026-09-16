"""Learning Loop: rating 1-5 → adjust routing keywords di PostgreSQL."""
from sqlalchemy import create_engine, select, func, delete
from dotenv import load_dotenv
import os
from core.models_feedback import Feedback
from config.routing_keywords_pg import get_routing_keywords

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

BAD_RATING_THRESHOLD = 3  # rating <= 3 = agen salah routing

def analyze_feedback():
    """Analisis feedback untuk detect routing error."""
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    
    with SessionLocal() as db:
        # Cari agen dengan rating rendah
        results = db.execute(
            select(Feedback.agent_type, Feedback.session_id, Feedback.rating)
            .where(Feedback.rating <= BAD_RATING_THRESHOLD)
            .order_by(Feedback.created_at.desc())
            .limit(50)
        ).all()
        
    return results

def extract_user_input_from_session(session_id: str):
    """Ambil user input dari session_memory untuk analisis."""
    from sqlalchemy.orm import sessionmaker
    from core.models import SessionMemory
    SessionLocal = sessionmaker(bind=engine)
    
    with SessionLocal() as db:
        result = db.execute(
            select(SessionMemory.content)
            .where(SessionMemory.session_id == session_id, SessionMemory.role == 'user')
            .order_by(SessionMemory.timestamp.asc())
            .limit(1)
        ).scalar_one_or_none()
    return result

def adjust_routing_from_feedback():
    """Adjust routing keywords berdasarkan feedback rating rendah."""
    bad_feedback = analyze_feedback()
    if not bad_feedback:
        print("[LEARNING] Tidak ada feedback rating rendah")
        return
    
    keywords_db, default = get_routing_keywords()
    
    for agent_type, session_id, rating in bad_feedback:
        user_input = extract_user_input_from_session(session_id)
        if not user_input:
            continue
        
        # Cek apakah input mengandung keyword yang tidak ada di agen saat ini
        for other_agent, keywords in keywords_db.items():
            if other_agent == agent_type:
                continue
            if any(kw in user_input.lower() for kw in keywords):
                print(f"[LEARNING] Input '{user_input[:50]}' seharusnya ke {other_agent} (rating: {rating})")
                # Tambahkan kata kunci dari input ke agen yang benar
                # (bisa diimplementasikan lebih lanjut)
    
    print(f"[LEARNING] Selesai analisis {len(bad_feedback)} feedback")

if __name__ == "__main__":
    adjust_routing_from_feedback()
