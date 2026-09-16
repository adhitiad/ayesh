import schedule
import time
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def cleanup_job():
    with engine.connect() as conn:
        conn.execute(text("SELECT cleanup_old_logs();"))
        conn.commit()
    print("[RETENTION] Old logs cleaned")

def learning_job():
    from core.learning_loop import adjust_routing_from_feedback
    adjust_routing_from_feedback()

schedule.every().day.at("02:00").do(cleanup_job)
schedule.every().day.at("03:00").do(learning_job)

if __name__ == "__main__":
    print("[RETENTION] Scheduler started")
    while True:
        schedule.run_pending()
        time.sleep(60)
