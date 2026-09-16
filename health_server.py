from flask import Flask, request, jsonify
from core.observability import health_check, get_metrics
from core.models_feedback import Feedback
from sqlalchemy import create_engine, select, func
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

app = Flask(__name__)

@app.route('/health')
def health():
    status = health_check()
    return jsonify({
        "postgres": {"status": "up" if status.postgres else "down", "latency_ms": round(status.db_latency_ms, 2)},
        "redis": {"status": "up" if status.redis else "down", "latency_ms": round(status.redis_latency_ms, 2)}
    })

@app.route('/metrics')
def metrics():
    return jsonify(get_metrics())

@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.json
    session_id = data.get('session_id', '')
    agent_type = data.get('agent_type', '')
    rating = data.get('rating', 0)
    comment = data.get('comment', '')
    
    if not (1 <= rating <= 5):
        return jsonify({"error": "rating harus 1-5"}), 400
    
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        fb = Feedback(session_id=session_id, agent_type=agent_type, rating=rating, comment=comment)
        db.add(fb)
        db.commit()
    return jsonify({"status": "ok", "rating": rating})

@app.route('/feedback/stats')
def feedback_stats():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        results = db.execute(
            select(Feedback.agent_type, func.avg(Feedback.rating), func.count())
            .group_by(Feedback.agent_type)
        ).all()
    stats = {}
    for agent, avg_rating, count in results:
        stats[agent] = {"avg_rating": round(float(avg_rating), 2), "total": count}
    return jsonify(stats)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
