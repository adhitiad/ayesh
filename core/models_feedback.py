from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Feedback(Base):
    __tablename__ = 'feedback'
    id = Column(Integer, primary_key=True)
    session_id = Column(String(100), nullable=False, index=True)
    agent_type = Column(String(50))
    rating = Column(Integer)  # 1-5
    comment = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
